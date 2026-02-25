from __future__ import annotations

from dataclasses import dataclass
import re

from demi_consultant.state.user_session import UserSession


@dataclass(slots=True)
class OnboardingDecision:
    handled: bool
    reply: str | None = None


class OnboardingService:
    _name_pattern = re.compile(r"^[A-Za-zА-Яа-яЁё]{2,20}$")
    _age_extract_pattern = re.compile(r"(\d{1,3})")

    START_MESSAGE = (
        "Здравствуйте 🤍\n"
        "Я — AI косметолог-консультант Demi Results.\n\n"
        "Помогу:\n"
        "• определить тип кожи\n"
        "• разобрать проблемы (акне, сухость, жирность и т.д.)\n"
        "• подобрать правильный уход\n"
        "• объяснить составы простым языком\n\n"
        "Для начала давайте познакомимся.\n"
        "Как к Вам можно обращаться?"
    )

    NAME_INVALID_MESSAGE = "Введите, пожалуйста, только имя (без пробелов)."
    AGE_INVALID_MESSAGE = "Введите корректный возраст числом от 12 до 90."

    def handle_text(self, session: UserSession, text: str) -> OnboardingDecision:
        # Self-heal inconsistent session states after restarts.
        if session.name and session.age is not None and not session.onboarding_completed:
            session.age_range = self._to_age_range(session.age)
            session.onboarding_completed = True
            session.onboarding_step = "done"
            session.menu_active = True
            session.menu_shown_once = False
            return OnboardingDecision(handled=False)

        if session.onboarding_completed:
            return OnboardingDecision(handled=False)

        if session.onboarding_step is None:
            session.onboarding_step = "name"
            return OnboardingDecision(handled=True, reply=self.START_MESSAGE)

        if session.onboarding_step == "name":
            name = self._parse_name(text)
            if name is None:
                return OnboardingDecision(handled=True, reply=self.NAME_INVALID_MESSAGE)

            session.name = name
            session.onboarding_step = "age"
            return OnboardingDecision(
                handled=True,
                reply=(
                    f"Спасибо, {name} 🤍\n"
                    "Чтобы рекомендации были точнее — подскажите, пожалуйста, Ваш возраст."
                ),
            )

        if session.onboarding_step == "age":
            age = self._parse_age(text)
            if age is None:
                return OnboardingDecision(handled=True, reply=self.AGE_INVALID_MESSAGE)

            session.age = age
            session.age_range = self._to_age_range(age)
            session.onboarding_completed = True
            session.onboarding_step = "done"
            session.menu_active = True
            session.menu_shown_once = False

            return OnboardingDecision(
                handled=True,
                reply=(
                    f"Приятно познакомиться, {session.name}.\n"
                    "Теперь могу дать более персональные рекомендации ✨\n\n"
                    "С чего начнём?"
                ),
            )

        return OnboardingDecision(handled=False)

    def _parse_name(self, text: str) -> str | None:
        normalized = " ".join(text.split())
        if " " in normalized:
            return None
        if not self._name_pattern.fullmatch(normalized):
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
