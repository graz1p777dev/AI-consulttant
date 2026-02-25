from __future__ import annotations

from dataclasses import dataclass
import re
from time import time

from demi_consultant.core.config import Settings
from demi_consultant.state.user_session import UserSession
from demi_consultant.transport.rate_limit import RateLimiter


@dataclass(slots=True)
class InputGuardDecision:
    allowed: bool
    response: str | None = None
    ignore: bool = False
    token_multiplier: float = 1.0
    forced_verbosity: str | None = None


class InteractionGuardService:
    _repeat_chars_pattern = re.compile(r"(.)\1{6,}")
    _only_punctuation_pattern = re.compile(r"^[\W_]+$", re.UNICODE)
    _only_emoji_pattern = re.compile(r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\s]+$")

    _low_value_messages = {
        "ок",
        "ok",
        "понял",
        "поняла",
        "понятно",
        "спасибо",
        "thanks",
        "thank you",
        "ясно",
    }

    def __init__(self, settings: Settings, rate_limiter: RateLimiter) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter

    def check_text(
        self,
        session: UserSession,
        user_id: str,
        text: str,
        *,
        event_ts: float | None = None,
        onboarding_incomplete: bool = False,
    ) -> InputGuardDecision:
        now = event_ts if event_ts is not None else time()

        block_decision = self._check_common_limits(session, user_id, now)
        if block_decision is not None:
            return block_decision

        if len(text) > self._settings.max_user_text_length:
            return InputGuardDecision(
                allowed=False,
                response=(
                    "Сообщение слишком длинное.\n"
                    f"Пожалуйста, опишите вопрос кратко (до {self._settings.max_user_text_length} символов)."
                ),
            )

        token_multiplier = 1.0
        forced_verbosity: str | None = None
        if self._settings.near_limit_text_length <= len(text) <= self._settings.max_user_text_length:
            token_multiplier = 0.8
            forced_verbosity = "low"

        normalized = self._normalize(text)

        if onboarding_incomplete:
            return InputGuardDecision(
                allowed=True,
                token_multiplier=token_multiplier,
                forced_verbosity=forced_verbosity,
            )

        anti_spam_active = session.total_messages_received > 5

        if anti_spam_active:
            repeat_count = session.track_repeat(normalized)
            if repeat_count == 3:
                return InputGuardDecision(allowed=False, ignore=True)
            if repeat_count >= 5:
                session.muted_until = now + self._settings.repeat_mute_seconds
                return InputGuardDecision(
                    allowed=False,
                    ignore=True,
                )

        if self._is_meaningless(normalized):
            return InputGuardDecision(
                allowed=False,
                response=(
                    "Похоже, сообщение не распознано.\n"
                    "Опишите вопрос текстом — помогу разобраться."
                ),
            )

        if normalized in self._low_value_messages:
            return InputGuardDecision(
                allowed=False,
                response=(
                    "Пожалуйста 🤍\n"
                    "Если появятся вопросы по коже — я рядом."
                ),
            )

        return InputGuardDecision(
            allowed=True,
            token_multiplier=token_multiplier,
            forced_verbosity=forced_verbosity,
        )

    def check_image(
        self,
        session: UserSession,
        user_id: str,
        *,
        caption: str,
        image_size: int,
        event_ts: float | None = None,
    ) -> InputGuardDecision:
        now = event_ts if event_ts is not None else time()

        block_decision = self._check_common_limits(session, user_id, now)
        if block_decision is not None:
            return block_decision

        if len(caption) > self._settings.max_user_text_length:
            return InputGuardDecision(
                allowed=False,
                response=(
                    "Сообщение слишком длинное.\n"
                    f"Пожалуйста, сократите подпись к фото до {self._settings.max_user_text_length} символов."
                ),
            )

        if session.images_in_session >= self._settings.max_images_per_session:
            return InputGuardDecision(
                allowed=False,
                response=(
                    "Давайте остановимся на текущем фото,\n"
                    "я уже могу дать рекомендации."
                ),
            )

        if session.last_image_at and now - session.last_image_at < self._settings.image_rate_limit_seconds:
            return InputGuardDecision(
                allowed=False,
                response=(
                    "Фото приходят слишком часто.\n"
                    f"Отправляйте не чаще 1 фото в {self._settings.image_rate_limit_seconds} секунд."
                ),
            )

        if image_size > self._settings.max_image_size_bytes:
            return InputGuardDecision(
                allowed=False,
                response=(
                    "Файл слишком большой.\n"
                    f"Максимальный размер: {self._settings.max_image_size_mb} MB."
                ),
            )

        session.register_image(now)

        token_multiplier = 1.0
        forced_verbosity: str | None = None
        if self._settings.near_limit_text_length <= len(caption) <= self._settings.max_user_text_length:
            token_multiplier = 0.8
            forced_verbosity = "low"

        return InputGuardDecision(
            allowed=True,
            token_multiplier=token_multiplier,
            forced_verbosity=forced_verbosity,
        )

    def _check_common_limits(
        self,
        session: UserSession,
        user_id: str,
        now: float,
    ) -> InputGuardDecision | None:
        if now < session.blocked_until:
            return InputGuardDecision(allowed=False, ignore=True)

        message_rate = session.register_message(now, window_seconds=self._settings.abuse_window_seconds)
        anti_spam_active = session.total_messages_received > 5

        if anti_spam_active and message_rate > self._settings.abuse_max_messages:
            session.blocked_until = now + self._settings.abuse_block_seconds
            return InputGuardDecision(
                allowed=False,
                ignore=True,
            )

        if anti_spam_active and now < session.muted_until:
            return InputGuardDecision(allowed=False, ignore=True)

        if anti_spam_active:
            rate_verdict = self._rate_limiter.check(user_id, event_ts=now)
            if not rate_verdict.allowed:
                return InputGuardDecision(
                    allowed=False,
                    ignore=True,
                )

        return None

    def _is_meaningless(self, normalized_text: str) -> bool:
        if not normalized_text:
            return True
        if self._repeat_chars_pattern.search(normalized_text):
            return True
        if self._only_punctuation_pattern.fullmatch(normalized_text):
            return True
        if self._only_emoji_pattern.fullmatch(normalized_text):
            return True
        return False

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split()).strip()
