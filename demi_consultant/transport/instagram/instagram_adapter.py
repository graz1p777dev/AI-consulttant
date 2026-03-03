from __future__ import annotations

import logging
import mimetypes
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from demi_consultant.core.config import Settings
from demi_consultant.core.exceptions import MetaAPIError, PayloadValidationError
from demi_consultant.core.logger import log_extra
from demi_consultant.integrations.meta_api.instagram_client import InstagramClient
from demi_consultant.services.consultation_service import ConsultationService
from demi_consultant.services.localization import text as tr
from demi_consultant.transport.base_channel_adapter import BaseChannelAdapter
from demi_consultant.transport.meta.message_normalizer import normalize_instagram_payload

logger = logging.getLogger(__name__)


class InstagramAdapter(BaseChannelAdapter):
    def __init__(
        self,
        *,
        settings: Settings,
        consultation_service: ConsultationService,
        instagram_client: InstagramClient,
    ) -> None:
        self._settings = settings
        self._consultation_service = consultation_service
        self._instagram_client = instagram_client
        self.app = FastAPI(title="Demi Consultant Instagram Webhook")
        self._register_routes()

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
            channel="instagram",
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
            channel="instagram",
            image_mime_type=image_mime_type,
            event_ts=event_ts,
        )

    async def handle_audio(
        self,
        user_id: str,
        audio_bytes: bytes,
        *,
        audio_mime_type: str | None,
        source_name: str,
        event_ts: float | None = None,
    ) -> str:
        session = self._consultation_service.get_session(user_id)

        try:
            transcript = await self._consultation_service.transcribe_audio(
                audio_bytes=audio_bytes,
                file_name=source_name,
                mime_type=audio_mime_type,
                language=session.language,
            )
        except Exception as exc:  # pragma: no cover - transport safety net
            logger.exception(
                "Instagram audio transcription failed: %s",
                exc,
                extra=log_extra(channel="instagram", user_id=user_id),
            )
            return tr("technical_error", session.language)

        transcript_text = transcript.strip()
        if not transcript_text:
            return tr("meaningless", session.language)

        try:
            return (
                await self.handle_text(
                    user_id,
                    transcript_text,
                    event_ts=event_ts,
                    model_name_override=self._settings.voice_reply_model,
                )
                or tr("technical_error", session.language)
            )
        except Exception as exc:  # pragma: no cover - transport safety net
            logger.exception(
                "Instagram transcribed audio handling failed: %s",
                exc,
                extra=log_extra(channel="instagram", user_id=user_id),
            )
            return tr("technical_error", session.language)

    @staticmethod
    def _audio_filename(*, media_id: str | None, mime_type: str | None) -> str:
        normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
        extension = mimetypes.guess_extension(normalized_mime) or ".ogg"
        media_suffix = (media_id or "message").replace("/", "_")
        return f"instagram_audio_{media_suffix}{extension}"

    def _register_routes(self) -> None:
        @self.app.get("/webhook")
        async def verify_webhook(request: Request) -> PlainTextResponse:
            mode = request.query_params.get("hub.mode")
            verify_token = request.query_params.get("hub.verify_token")
            challenge = request.query_params.get("hub.challenge", "")

            if mode == "subscribe" and verify_token == self._settings.instagram_verify_token:
                return PlainTextResponse(challenge)
            raise HTTPException(status_code=403, detail="Webhook verification failed")

        @self.app.post("/webhook")
        async def receive_webhook(request: Request) -> JSONResponse:
            raw_body = await request.body()
            signature = request.headers.get("X-Hub-Signature-256")
            if not self._instagram_client.verify_signature(raw_body, signature):
                raise HTTPException(status_code=403, detail="Invalid webhook signature")

            try:
                payload: dict[str, Any] = await request.json()
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Malformed JSON payload") from exc

            try:
                messages = normalize_instagram_payload(payload)
            except PayloadValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            if not messages:
                return JSONResponse({"status": "ignored"})

            for message in messages:
                try:
                    await self._instagram_client.send_typing(message.user_id)

                    if message.text is not None and message.text.strip():
                        reply = await self.handle_text(message.user_id, message.text)
                    elif message.media_url:
                        media_bytes, downloaded_mime_type = await self._instagram_client.download_media_url(
                            message.media_url
                        )
                        resolved_mime = message.mime_type or downloaded_mime_type
                        is_audio = (message.media_kind == "audio") or resolved_mime.lower().startswith(
                            "audio/"
                        )
                        if is_audio:
                            reply = await self.handle_audio(
                                message.user_id,
                                media_bytes,
                                audio_mime_type=resolved_mime,
                                source_name=self._audio_filename(
                                    media_id=message.media_id,
                                    mime_type=resolved_mime,
                                ),
                            )
                        else:
                            reply = await self.handle_image(
                                message.user_id,
                                media_bytes,
                                caption=message.caption,
                                image_mime_type=resolved_mime,
                            )
                    elif message.media_id:
                        media_bytes, downloaded_mime_type = await self._instagram_client.download_media(
                            message.media_id
                        )
                        resolved_mime = message.mime_type or downloaded_mime_type
                        is_audio = (message.media_kind == "audio") or resolved_mime.lower().startswith(
                            "audio/"
                        )
                        if is_audio:
                            reply = await self.handle_audio(
                                message.user_id,
                                media_bytes,
                                audio_mime_type=resolved_mime,
                                source_name=self._audio_filename(
                                    media_id=message.media_id,
                                    mime_type=resolved_mime,
                                ),
                            )
                        else:
                            reply = await self.handle_image(
                                message.user_id,
                                media_bytes,
                                caption=message.caption,
                                image_mime_type=resolved_mime,
                            )
                    else:
                        reply = None

                    if reply:
                        await self._instagram_client.send_text(message.user_id, reply)
                except MetaAPIError as exc:
                    logger.warning(
                        "Instagram Meta API error: %s",
                        exc,
                        extra=log_extra(channel="instagram", user_id=message.user_id),
                    )
                    try:
                        await self._instagram_client.send_text(
                            message.user_id,
                            "Вижу техническую ошибку. Попробуйте через минуту.",
                        )
                    except Exception:
                        logger.exception(
                            "Failed to deliver Instagram fallback message",
                            extra=log_extra(channel="instagram", user_id=message.user_id),
                        )
                except Exception as exc:  # pragma: no cover - transport safety net
                    logger.exception(
                        "Instagram webhook processing failed: %s",
                        exc,
                        extra=log_extra(channel="instagram", user_id=message.user_id),
                    )

            return JSONResponse({"status": "ok"})
