from __future__ import annotations

from dataclasses import dataclass
import re

from demi_consultant.services.localization import (
    DEFAULT_LANGUAGE,
    normalize_language,
    resolve_language_choice,
    text as tr,
)
from demi_consultant.state.user_session import UserSession

BAD_NAMES = {"asdf", "qwerty", "ывфывф", "123", "admin"}


def validate_name(name: str) -> bool:
    name = name.strip()

    if len(name) < 2 or len(name) > 20:
        return False

    if not name.isalpha():
        return False

    if name.lower() in BAD_NAMES:
        return False

    return True


@dataclass(slots=True)
class OnboardingDecision:
    handled: bool
    reply: str | None = None


class OnboardingService:
    _name_pattern = re.compile(r"^[^\W\d_]{2,20}$", re.UNICODE)
    _age_extract_pattern = re.compile(r"(\d{1,3})")

    START_MESSAGE = tr("language_prompt", DEFAULT_LANGUAGE)

    def handle_text(self, session: UserSession, text: str) -> OnboardingDecision:
        # Self-heal inconsistent session states after restarts.
        if session.name and session.age is not None and not session.onboarding_completed:
            session.language = normalize_language(session.language)
            session.age_range = self._to_age_range(session.age)
            session.onboarding_completed = True
            session.onboarding_step = "done"
            session.menu_active = True
            session.menu_shown_once = False
            return OnboardingDecision(handled=False)

        if session.onboarding_completed:
            return OnboardingDecision(handled=False)

        if session.onboarding_step is None:
            session.onboarding_step = "language"
            return OnboardingDecision(handled=True, reply=self.START_MESSAGE)

        if session.onboarding_step == "language":
            selected_language = resolve_language_choice(text)
            if selected_language is None:
                return OnboardingDecision(
                    handled=True,
                    reply=tr("language_invalid", session.language),
                )
            session.language = selected_language
            session.onboarding_step = "name"
            return OnboardingDecision(
                handled=True,
                reply=tr("language_ack_name", session.language),
            )

        if session.onboarding_step == "name":
            name = self._parse_name(text)
            if name is None:
                return OnboardingDecision(
                    handled=True,
                    reply=tr("name_invalid", session.language),
                )

            session.name = name
            session.onboarding_step = "age"
            return OnboardingDecision(
                handled=True,
                reply=tr("ask_age", session.language, name=name),
            )

        if session.onboarding_step == "age":
            age = self._parse_age(text)
            if age is None:
                return OnboardingDecision(
                    handled=True,
                    reply=tr("age_invalid", session.language),
                )

            session.age = age
            session.age_range = self._to_age_range(age)
            session.onboarding_completed = True
            session.onboarding_step = "done"
            session.menu_active = True
            session.menu_shown_once = False

            return OnboardingDecision(
                handled=True,
                reply=tr("onboarding_done", session.language, name=session.name or ""),
            )

        return OnboardingDecision(handled=False)

    def _parse_name(self, text: str) -> str | None:
        normalized = " ".join(text.split())
        if " " in normalized:
            return None
        if not self._name_pattern.fullmatch(normalized):
            return None
        if not validate_name(normalized):
            return None
        return normalized.capitalize()

    @staticmethod
    def _parse_age(text: str) -> int | None:
        normalized = text.strip()
        if normalized.isdigit():
            age = int(normalized)
        else:
            match = OnboardingService._age_extract_pattern.search(normalized)
            if match is None:
                return None
            age = int(match.group(1))
        if age < 12 or age > 90:
            return None
        return age

    @staticmethod
    def _to_age_range(age: int) -> str:
        if age < 18:
            return "<18"
        if age <= 24:
            return "18-24"
        if age <= 34:
            return "25-34"
        if age <= 44:
            return "35-44"
        return "45+"
