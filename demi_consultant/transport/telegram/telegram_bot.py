from __future__ import annotations

import asyncio
import html
import hashlib
import logging
import re
from pathlib import Path
from tempfile import gettempdir
from time import monotonic

from telegram import Message, ReplyKeyboardRemove, Update
from telegram.error import BadRequest, Conflict, TelegramError
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.ext import MessageHandler as PTBMessageHandler
from telegram.ext import filters

from demi_consultant.core.config import Settings
from demi_consultant.core.exceptions import ProcessLockError
from demi_consultant.core.logger import log_extra
from demi_consultant.core.process_lock import ProcessLock
from demi_consultant.services.consultation_service import ConsultationService
from demi_consultant.services.localization import menu_labels_normalized, normalize_language, text as tr
from demi_consultant.transport.base_channel_adapter import BaseChannelAdapter
from demi_consultant.transport.telegram.handlers.error_handler import global_error_handler
from demi_consultant.transport.telegram.handlers.start_handler import StartHandler
from demi_consultant.transport.telegram.keyboards.main import build_language_keyboard, build_main_keyboard

logger = logging.getLogger(__name__)


class TelegramCosmoBot(BaseChannelAdapter):
    _TELEGRAM_REPLY_SOFT_LIMIT = 3900
    _BOLD_MARKER_PATTERN = re.compile(r"\*([^*\n]+)\*")
    _START_DEDUP_WINDOW_SECONDS = 1.5
    _POLLING_RETRY_SECONDS = 5

    def __init__(self, settings: Settings, consultation_service: ConsultationService) -> None:
        if not settings.telegram_token:
            raise ValueError("TELEGRAM_TOKEN is not configured")

        self._settings = settings
        self._consultation_service = consultation_service
        self._active_users: set[str] = set()
        self._queued_busy_messages: dict[str, list[Message]] = {}
        self._last_start_events: dict[str, tuple[int, float]] = {}
        self._active_users_lock = asyncio.Lock()

        builder = (
            ApplicationBuilder()
            .token(settings.telegram_token)
            .connect_timeout(20)
            .read_timeout(20)
            .write_timeout(20)
            .pool_timeout(20)
            .concurrent_updates(8)
        )
        if settings.telegram_proxy_url:
            builder = builder.proxy(settings.telegram_proxy_url).get_updates_proxy(
                settings.telegram_proxy_url
            )
            logger.info("Telegram proxy enabled for bot API traffic")

        self._application = builder.build()
        self._start_handler = StartHandler()

    async def handle_text(
        self,
        user_id: str,
        text: str,
        *,
        event_ts: float | None = None,
        model_name_override: str | None = None,
    ) -> str | None:
        return await self._consultation_service.process_message(
            user_id=user_id,
            text=text,
            channel="telegram",
            model_name_override=model_name_override,
            event_ts=event_ts,
        )

    async def handle_image(
        self,
        user_id: str,
        image_bytes: bytes,
        *,
        caption: str | None,
        image_mime_type: str,
        event_ts: float | None = None,
    ) -> str | None:
        return await self._consultation_service.process_photo(
            user_id=user_id,
            image_bytes=image_bytes,
            caption=caption,
            channel="telegram",
            image_mime_type=image_mime_type,
            event_ts=event_ts,
        )

    def _register_handlers(self) -> None:
        self._application.add_handler(CommandHandler("start", self._on_start))
        self._application.add_handler(
            PTBMessageHandler(filters.Regex(r"^/start(?:@\w+)?$"), self._on_start)
        )
        self._application.add_handler(PTBMessageHandler(filters.PHOTO, self._on_photo))
        self._application.add_handler(PTBMessageHandler(filters.VOICE | filters.AUDIO, self._on_voice))
        self._application.add_handler(
            PTBMessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text)
        )
        self._application.add_error_handler(global_error_handler)

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None:
            return
        if update.message is None:
            return

        user_id = str(update.effective_user.id)
        logger.info("Received /start command", extra=log_extra(channel="telegram", user_id=user_id))
        now = monotonic()
        message_id = update.message.message_id
        last_start = self._last_start_events.get(user_id)
        if last_start is not None:
            last_message_id, last_ts = last_start
            if message_id == last_message_id:
                return
            if now - last_ts < self._START_DEDUP_WINDOW_SECONDS:
                return
        self._last_start_events[user_id] = (message_id, now)

        session = self._consultation_service.get_session(user_id)
        if session.onboarding_completed:
            await update.message.reply_text(
                tr("start_returning_user", session.language),
                reply_to_message_id=update.message.message_id,
            )
            return
        self._consultation_service.start_onboarding(user_id)
        await self._start_handler(update, context)

    async def _on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.message.text is None or update.effective_user is None:
            return

        source_message = update.message
        user_id = str(update.effective_user.id)
        text = source_message.text.strip() # pyright: ignore[reportOptionalMemberAccess]
        session_before = self._consultation_service.get_session(user_id)
        pending_message: Message | None = None
        acquired = False

        acquired = await self._try_begin_user_processing(user_id)
        if not acquired:
            await self._send_busy_message(source_message, user_id, session_before.language)
            return

        try:
            if self._should_show_thinking(session_before, text):
                pending_message = await self._send_thinking_message(source_message, session_before.language)

            try:
                reply = await self.handle_text(
                    user_id,
                    text,
                    event_ts=self._event_timestamp(source_message),
                )
            except Exception as exc:  # pragma: no cover - transport safety net
                logger.exception(
                    "Telegram text handling failed: %s",
                    exc,
                    extra=log_extra(channel="telegram", user_id=user_id),
                )
                reply = tr("technical_error", session_before.language)

            if not reply:
                if pending_message is not None:
                    await self._dismiss_pending_message(pending_message)
                return

            session = self._consultation_service.get_session(user_id)
            reply_markup = self._select_reply_markup(session, text)
            if pending_message is not None:
                replaced = await self._replace_pending_with_reply(
                    pending_message,
                    reply,
                    reply_markup=reply_markup,
                )
                if replaced:
                    return
                await self._dismiss_pending_message(pending_message)

            await self._send_reply(source_message, reply, reply_markup=reply_markup)
        finally:
            if acquired:
                await self._finish_user_processing(user_id)

    async def _on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None or not update.message.photo:
            return

        source_message = update.message
        user_id = str(update.effective_user.id)
        session_before = self._consultation_service.get_session(user_id)
        pending_message: Message | None = None
        acquired = False

        acquired = await self._try_begin_user_processing(user_id)
        if not acquired:
            await self._send_busy_message(source_message, user_id, session_before.language)
            return

        try:
            if session_before.onboarding_completed:
                pending_message = await self._send_thinking_message(source_message, session_before.language)

            photo = source_message.photo[-1]
            photo_file = await photo.get_file()
            photo_bytes = bytes(await photo_file.download_as_bytearray())
            caption = (source_message.caption or "").strip() or None

            try:
                reply = await self.handle_image(
                    user_id,
                    photo_bytes,
                    caption=caption,
                    image_mime_type="image/jpeg",
                    event_ts=self._event_timestamp(source_message),
                )
            except Exception as exc:  # pragma: no cover - transport safety net
                logger.exception(
                    "Telegram photo handling failed: %s",
                    exc,
                    extra=log_extra(channel="telegram", user_id=user_id),
                )
                reply = tr("technical_error", session_before.language)

            if not reply:
                if pending_message is not None:
                    await self._dismiss_pending_message(pending_message)
                return

            if pending_message is not None:
                replaced = await self._replace_pending_with_reply(pending_message, reply)
                if replaced:
                    return
                await self._dismiss_pending_message(pending_message)

            await self._send_reply(source_message, reply)
        finally:
            if acquired:
                await self._finish_user_processing(user_id)

    async def _on_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return

        source_message = update.message
        if source_message.voice is None and source_message.audio is None:
            return

        user_id = str(update.effective_user.id)
        session_before = self._consultation_service.get_session(user_id)
        pending_message: Message | None = None
        acquired = False
        transcript_text = ""

        acquired = await self._try_begin_user_processing(user_id)
        if not acquired:
            await self._send_busy_message(source_message, user_id, session_before.language)
            return

        try:
            if session_before.onboarding_completed:
                pending_message = await self._send_thinking_message(source_message, session_before.language)

            try:
                audio_bytes, file_name, mime_type = await self._download_audio_payload(source_message)
            except Exception as exc:  # pragma: no cover - transport safety net
                logger.exception(
                    "Telegram audio download failed: %s",
                    exc,
                    extra=log_extra(channel="telegram", user_id=user_id),
                )
                reply = tr("technical_error", session_before.language)
            else:
                if not audio_bytes:
                    reply = tr("meaningless", session_before.language)
                else:
                    try:
                        transcript_text = await self._consultation_service.transcribe_audio(
                            audio_bytes=audio_bytes,
                            file_name=file_name,
                            mime_type=mime_type,
                            language=session_before.language,
                        )
                    except Exception as exc:  # pragma: no cover - transport safety net
                        logger.exception(
                            "Telegram audio transcription failed: %s",
                            exc,
                            extra=log_extra(channel="telegram", user_id=user_id),
                        )
                        reply = tr("technical_error", session_before.language)
                    else:
                        if not transcript_text:
                            reply = tr("meaningless", session_before.language)
                        else:
                            try:
                                reply = await self.handle_text(
                                    user_id,
                                    transcript_text,
                                    model_name_override=self._settings.voice_reply_model,
                                    event_ts=self._event_timestamp(source_message),
                                )
                            except Exception as exc:  # pragma: no cover - transport safety net
                                logger.exception(
                                    "Telegram voice message handling failed: %s",
                                    exc,
                                    extra=log_extra(channel="telegram", user_id=user_id),
                                )
                                reply = tr("technical_error", session_before.language)

            if not reply:
                if pending_message is not None:
                    await self._dismiss_pending_message(pending_message)
                return

            session = self._consultation_service.get_session(user_id)
            reply_markup = self._select_reply_markup(session, transcript_text)
            if pending_message is not None:
                replaced = await self._replace_pending_with_reply(
                    pending_message,
                    reply,
                    reply_markup=reply_markup,
                )
                if replaced:
                    return
                await self._dismiss_pending_message(pending_message)

            await self._send_reply(source_message, reply, reply_markup=reply_markup)
        finally:
            if acquired:
                await self._finish_user_processing(user_id)

    def _select_reply_markup(self, session, user_text: str):
        if not session.onboarding_completed and session.onboarding_step == "language":
            return build_language_keyboard()

        if session.menu_active and not session.menu_shown_once:
            session.menu_shown_once = True
            return build_main_keyboard(normalize_language(session.language))

        normalized = self._normalize_menu_text(user_text)
        menu_labels = menu_labels_normalized(session.language)
        if session.menu_active and normalized in menu_labels:
            session.menu_active = False
            return ReplyKeyboardRemove()

        return None

    async def _send_reply(self, source_message: Message, reply: str, reply_markup=None) -> None:
        chunks = self._split_reply_chunks(reply, max_chars=self._TELEGRAM_REPLY_SOFT_LIMIT)

        for index, chunk in enumerate(chunks):
            html_chunk = self._to_telegram_html(chunk)
            chunk_markup = reply_markup if index == 0 else None
            try:
                await source_message.reply_text(
                    html_chunk,
                    reply_markup=chunk_markup,
                    parse_mode="HTML",
                    reply_to_message_id=source_message.message_id,
                )
            except BadRequest:
                await source_message.reply_text(
                    chunk,
                    reply_markup=chunk_markup,
                    reply_to_message_id=source_message.message_id,
                )

    @classmethod
    def _to_telegram_html(cls, text: str) -> str:
        if not text:
            return ""
        fragments: list[str] = []
        cursor = 0
        for match in cls._BOLD_MARKER_PATTERN.finditer(text):
            start, end = match.span()
            if start > cursor:
                fragments.append(html.escape(text[cursor:start]))
            fragments.append(f"<b>{html.escape(match.group(1))}</b>")
            cursor = end
        if cursor < len(text):
            fragments.append(html.escape(text[cursor:]))
        return "".join(fragments)

    @staticmethod
    def _split_reply_chunks(reply: str, *, max_chars: int) -> list[str]:
        text = (reply or "").strip()
        if not text:
            return [""]
        if len(text) <= max_chars:
            return [text]

        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            paragraphs = [text]

        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= max_chars:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            tail = paragraph
            while len(tail) > max_chars:
                split_at = tail.rfind(" ", 0, max_chars)
                if split_at < max_chars // 2:
                    split_at = max_chars
                piece = tail[:split_at].strip()
                if piece:
                    chunks.append(piece)
                tail = tail[split_at:].strip()
            current = tail

        if current:
            chunks.append(current)

        return chunks or [text]

    async def _send_thinking_message(self, source_message: Message, language: str | None) -> Message | None:
        try:
            return await source_message.reply_text(
                tr("thinking_message", language),
                reply_to_message_id=source_message.message_id,
            )
        except BadRequest:
            return None

    async def _send_busy_message(self, source_message: Message, user_id: str, language: str | None) -> None:
        async with self._active_users_lock:
            if user_id in self._queued_busy_messages:
                return
            # Reserve a slot so concurrent updates do not emit duplicate busy replies.
            self._queued_busy_messages[user_id] = []

        try:
            busy_message = await source_message.reply_text(
                tr("busy_message", language),
                reply_to_message_id=source_message.message_id,
            )
            async with self._active_users_lock:
                self._queued_busy_messages.setdefault(user_id, []).append(busy_message)
        except BadRequest:
            async with self._active_users_lock:
                if not self._queued_busy_messages.get(user_id):
                    self._queued_busy_messages.pop(user_id, None)
            return

    async def _try_begin_user_processing(self, user_id: str) -> bool:
        async with self._active_users_lock:
            if user_id in self._active_users:
                return False
            self._active_users.add(user_id)
            return True

    async def _finish_user_processing(self, user_id: str) -> None:
        queued_messages: list[Message] = []
        async with self._active_users_lock:
            self._active_users.discard(user_id)
            queued_messages = self._queued_busy_messages.pop(user_id, [])

        for message in queued_messages:
            await self._dismiss_pending_message(message)

    async def _dismiss_pending_message(self, pending_message: Message) -> None:
        try:
            await pending_message.delete()
        except BadRequest:
            return

    async def _replace_pending_with_reply(
        self,
        pending_message: Message,
        reply: str,
        *,
        reply_markup=None,
    ) -> bool:
        if reply_markup is not None:
            return False

        html_reply = self._to_telegram_html(reply)
        try:
            await pending_message.edit_text(html_reply, parse_mode="HTML")
            return True
        except BadRequest:
            return False

    def _should_show_thinking(self, session, user_text: str) -> bool:
        if not session.onboarding_completed:
            return False

        normalized = self._normalize_menu_text(user_text)
        if session.menu_active and normalized in menu_labels_normalized(session.language):
            return False

        return True

    @staticmethod
    def _normalize_menu_text(text: str) -> str:
        return " ".join(text.lower().split())

    @staticmethod
    def _event_timestamp(source_message: Message) -> float | None:
        if source_message.date is None:
            return None
        return source_message.date.timestamp()

    @staticmethod
    async def _download_audio_payload(source_message: Message) -> tuple[bytes, str, str | None]:
        if source_message.voice is not None:
            voice = source_message.voice
            voice_file = await voice.get_file()
            voice_bytes = bytes(await voice_file.download_as_bytearray())
            return (
                voice_bytes,
                f"voice_{source_message.message_id}.ogg",
                voice.mime_type or "audio/ogg",
            )

        if source_message.audio is not None:
            audio = source_message.audio
            audio_file = await audio.get_file()
            audio_bytes = bytes(await audio_file.download_as_bytearray())
            audio_name = (audio.file_name or f"audio_{source_message.message_id}.mp3").strip()
            return (audio_bytes, audio_name, audio.mime_type)

        return (b"", f"audio_{source_message.message_id}.ogg", None)

    def _build_polling_lock(self) -> ProcessLock:
        token = self._settings.telegram_token or ""
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        lock_path = Path(gettempdir()) / f"demi_consultant.telegram.{token_hash}.lock"
        return ProcessLock(lock_path)

    async def run_polling(self) -> None:
        self._register_handlers()
        lock = self._build_polling_lock()
        try:
            lock.acquire()
        except ProcessLockError:
            logger.error("Telegram polling already running for this bot token; duplicate instance stopped")
            return

        try:
            while True:
                stop_polling_event = asyncio.Event()
                conflict_seen = False

                def polling_error_callback(exc: TelegramError) -> None:
                    nonlocal conflict_seen
                    if isinstance(exc, Conflict):
                        if not conflict_seen:
                            conflict_seen = True
                            logger.error(
                                "Polling conflict: another getUpdates client is active; stopping this instance"
                            )
                        stop_polling_event.set()
                        return

                    logger.exception("Exception happened while polling for updates.", exc_info=exc)

                try:
                    await self._application.initialize()
                    try:
                        await self._application.bot.delete_webhook(drop_pending_updates=False)
                    except TelegramError as exc:
                        logger.warning("Could not delete Telegram webhook before polling: %s", exc)
                    await self._application.start()
                    bot_name = self._application.bot.username or "-"
                    logger.info("Telegram polling started for @%s", bot_name)
                    if self._application.updater is None:
                        raise RuntimeError("Telegram updater is not available")
                    await self._application.updater.start_polling(
                        drop_pending_updates=False,
                        error_callback=polling_error_callback,
                    )
                    await stop_polling_event.wait()
                except Conflict:
                    logger.error("Telegram polling conflict; polling loop stopped")
                    return
                except TelegramError as exc:
                    logger.warning(
                        "Telegram polling network/API error: %s. Retrying in %s seconds.",
                        exc,
                        self._POLLING_RETRY_SECONDS,
                    )
                except Exception as exc:  # pragma: no cover - transport safety net
                    logger.exception(
                        "Telegram polling crashed unexpectedly: %s. Retrying in %s seconds.",
                        exc,
                        self._POLLING_RETRY_SECONDS,
                    )
                finally:
                    await self._safe_stop_polling_stack()

                await asyncio.sleep(self._POLLING_RETRY_SECONDS)
        finally:
            await self._safe_stop_polling_stack()
            lock.release()

    async def _safe_stop_polling_stack(self) -> None:
        updater = self._application.updater
        if updater is not None and getattr(updater, "running", False):
            try:
                await updater.stop()
            except Exception:  # pragma: no cover - cleanup safety net
                logger.exception("Failed to stop Telegram updater cleanly")

        if bool(getattr(self._application, "running", False)):
            try:
                await self._application.stop()
            except Exception:  # pragma: no cover - cleanup safety net
                logger.exception("Failed to stop Telegram application cleanly")

        if bool(getattr(self._application, "initialized", False)):
            try:
                await self._application.shutdown()
            except Exception:  # pragma: no cover - cleanup safety net
                logger.exception("Failed to shutdown Telegram application cleanly")
