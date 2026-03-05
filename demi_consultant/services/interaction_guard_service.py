from __future__ import annotations

from dataclasses import dataclass
import re
from time import time

from langdetect import LangDetectException, detect

from demi_consultant.core.config import Settings
from demi_consultant.services.localization import text as tr
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
    _ALLOWED_LANGUAGES = {"ru", "en", "ky"}
    _repeat_chars_pattern = re.compile(r"(.)\1{6,}")
    _only_punctuation_pattern = re.compile(r"^[\W_]+$", re.UNICODE)
    _only_emoji_pattern = re.compile(r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\s]+$")
    _letters_only_long_pattern = re.compile(r"^[a-zA-Z]{15,}$")
    _many_digits_pattern = re.compile(r"\d{5,}")
    _many_same_chars_pattern = re.compile(r"(.)\1{5,}")
    _many_non_letters_pattern = re.compile(r"[^a-zA-Zа-яА-ЯёЁңүөҢҮӨ\s]{4,}")
    _long_consonant_cluster_pattern = re.compile(r"[bcdfghjklmnpqrstvwxyzйцкнгшщзхъфвпрлджчсмтб]{7,}", re.IGNORECASE)
    _language_chars_pattern = re.compile(r"^[a-zA-Zа-яА-ЯёЁңүөҢҮӨ\s.,!?;:'\"()\-]+$")
    _letter_pattern = re.compile(r"[a-zA-Zа-яА-ЯёЁңүөҢҮӨ]")
    _token_pattern = re.compile(r"[a-zA-Zа-яА-ЯёЁңүөҢҮӨ0-9]+")
    _url_pattern = re.compile(r"(https?://|www\.)", re.IGNORECASE)
    _keyboard_mash_markers = (
        "qwerty",
        "asdf",
        "zxcv",
        "йцукен",
        "фыва",
        "ячсм",
        "12345",
        "54321",
    )

    _low_value_messages = {
        "ок",
        "ok",
        "okay",
        "понял",
        "поняла",
        "понятно",
        "спасибо",
        "thanks",
        "thank you",
        "рахмат",
        "чоң рахмат",
        "ясно",
    }
    _BURST_WINDOW_SECONDS = 8
    _BURST_MAX_MESSAGES = 4
    _SOFT_BURST_MUTE_SECONDS = 18

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

        block_decision = self._check_common_limits(
            session,
            user_id,
            now,
            onboarding_incomplete=onboarding_incomplete,
        )
        if block_decision is not None:
            return block_decision

        if len(text) > self._settings.max_user_text_length:
            return InputGuardDecision(
                allowed=False,
                response=tr(
                    "text_too_long",
                    session.language,
                    limit=self._settings.max_user_text_length,
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

        repeat_count = session.track_repeat(normalized)
        if repeat_count == 3:
            return InputGuardDecision(allowed=False, ignore=True)
        if repeat_count >= 5:
            session.muted_until = now + self._settings.repeat_mute_seconds
            return InputGuardDecision(
                allowed=False,
                ignore=True,
            )

        if self._is_link_flood(text):
            return InputGuardDecision(
                allowed=False,
                response=tr("meaningless", session.language),
            )

        if self._is_meaningless(normalized):
            return InputGuardDecision(
                allowed=False,
                response=tr("meaningless", session.language),
            )

        if normalized in self._low_value_messages:
            return InputGuardDecision(
                allowed=False,
                response=tr("low_value", session.language),
            )

        if not self._input_guard(text):
            return InputGuardDecision(
                allowed=False,
                response=tr("meaningless", session.language),
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
                response=tr(
                    "caption_too_long",
                    session.language,
                    limit=self._settings.max_user_text_length,
                ),
            )

        if session.images_in_session >= self._settings.max_images_per_session:
            return InputGuardDecision(
                allowed=False,
                response=tr("images_limit", session.language),
            )

        if session.last_image_at and now - session.last_image_at < self._settings.image_rate_limit_seconds:
            return InputGuardDecision(
                allowed=False,
                response=tr(
                    "image_rate_limit",
                    session.language,
                    seconds=self._settings.image_rate_limit_seconds,
                ),
            )

        if image_size > self._settings.max_image_size_bytes:
            return InputGuardDecision(
                allowed=False,
                response=tr(
                    "image_size_limit",
                    session.language,
                    mb=self._settings.max_image_size_mb,
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
        *,
        onboarding_incomplete: bool = False,
    ) -> InputGuardDecision | None:
        if now < session.blocked_until:
            return InputGuardDecision(allowed=False, ignore=True)

        message_rate = session.register_message(now, window_seconds=self._settings.abuse_window_seconds)
        anti_spam_active = session.total_messages_received > 5

        if (not onboarding_incomplete) and session.total_messages_received >= 3 and self._is_fast_burst(session, now):
            session.muted_until = max(session.muted_until, now + self._SOFT_BURST_MUTE_SECONDS)
            return InputGuardDecision(allowed=False, ignore=True)

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

    def _looks_like_garbage(self, text: str) -> bool:
        normalized = text.strip()
        if len(normalized) < 3:
            return True
        if len(normalized) > 12 and " " not in normalized:
            return True
        if self._many_digits_pattern.search(normalized):
            return True
        if self._many_same_chars_pattern.search(normalized):
            return True
        if self._letters_only_long_pattern.fullmatch(normalized):
            return True
        lowered = normalized.lower()
        if any(marker in lowered for marker in self._keyboard_mash_markers):
            return True
        if self._many_non_letters_pattern.search(normalized):
            return True
        if self._long_consonant_cluster_pattern.search(lowered):
            return True
        if self._has_low_letter_density(normalized):
            return True
        if self._has_unstable_tokens(normalized):
            return True
        return False

    @staticmethod
    def _has_vowels(text: str) -> bool:
        vowels = "аеёиоуыэюяaeiouөү"
        return any(char in vowels for char in text.lower())

    def _has_language_like_text(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False
        if not self._language_chars_pattern.fullmatch(normalized):
            return False
        letters = self._letter_pattern.findall(normalized)
        if len(letters) < 2:
            return False
        letter_ratio = len(letters) / max(len(normalized), 1)
        if letter_ratio < 0.45:
            return False
        tokens = [token for token in self._token_pattern.findall(normalized.lower()) if token]
        if not tokens:
            return False
        # Avoid random single-token mash: requires at least one meaningful token profile.
        meaningful_tokens = sum(1 for token in tokens if len(token) <= 14 and self._token_vowel_ratio(token) >= 0.2)
        return meaningful_tokens >= 1

    @classmethod
    def _has_language(cls, text: str) -> bool:
        try:
            return detect(text) in cls._ALLOWED_LANGUAGES
        except LangDetectException:
            return False

    def _input_guard(self, text: str) -> bool:
        if self._looks_like_garbage(text):
            return False
        if not self._has_vowels(text):
            return False
        if self._is_strict_garbage(text):
            return False
        if not self._has_language(text) and not self._has_language_like_text(text):
            return False
        return True

    def _is_strict_garbage(self, text: str) -> bool:
        normalized = " ".join(text.lower().split()).strip()
        if not normalized:
            return True
        tokens = [token for token in self._token_pattern.findall(normalized) if token]
        if not tokens:
            return True
        if len(tokens) == 1:
            token = tokens[0]
            if len(token) >= 10 and self._token_vowel_ratio(token) < 0.22:
                return True
            if len(token) >= 18 and token.isalpha():
                return True
        short_noise = sum(1 for token in tokens if len(token) <= 2)
        if short_noise >= max(3, len(tokens) // 2 + 1):
            return True
        return False

    @classmethod
    def _has_low_letter_density(cls, text: str) -> bool:
        letters = cls._letter_pattern.findall(text)
        if not text:
            return True
        return (len(letters) / len(text)) < 0.30

    def _has_unstable_tokens(self, text: str) -> bool:
        tokens = [token for token in self._token_pattern.findall(text.lower()) if token]
        if not tokens:
            return True
        bad = 0
        for token in tokens:
            if len(token) >= 9 and self._token_vowel_ratio(token) < 0.2:
                bad += 1
            elif len(token) >= 18 and token.isalpha():
                bad += 1
        return bad >= 2 or (len(tokens) == 1 and bad == 1)

    @staticmethod
    def _token_vowel_ratio(token: str) -> float:
        vowels = "аеёиоуыэюяaeiouөү"
        if not token:
            return 0.0
        vowel_count = sum(1 for ch in token if ch in vowels)
        return vowel_count / len(token)

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split()).strip()

    @classmethod
    def _is_link_flood(cls, text: str) -> bool:
        return len(cls._url_pattern.findall(text)) >= 3

    @classmethod
    def _is_fast_burst(cls, session: UserSession, now: float) -> bool:
        cutoff = now - cls._BURST_WINDOW_SECONDS
        recent_count = 0
        for ts in reversed(session.message_timestamps):
            if ts < cutoff:
                break
            recent_count += 1
            if recent_count >= cls._BURST_MAX_MESSAGES:
                return True
        return False
