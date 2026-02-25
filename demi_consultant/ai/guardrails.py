from __future__ import annotations

from dataclasses import dataclass
import re

from demi_consultant.core.exceptions import EmptyResponseError, GuardrailViolation
from demi_consultant.utils.text_utils import clean_response


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    message: str | None = None


class Guardrails:
    _code_keywords = {
        "код",
        "питон",
        "python",
        "javascript",
        "sql",
        "script",
        "программирование",
        "программа",
        "алгоритм",
        "функция",
        "fastapi",
        "django",
    }
    _code_patterns = (
        re.compile(r"\bнапиш[ие]\w*\s+.*\bфункц\w*", re.IGNORECASE),
        re.compile(r"\bфункц\w*\s+.*\b(числ|квадрат)\w*", re.IGNORECASE),
    )

    _offtopic_keywords = {
        "крипта",
        "ставки",
        "политика",
        "гороскоп",
        "астрология",
        "взлом",
    }

    _domain_keywords = {
        "кожа",
        "лицо",
        "акне",
        "прыщ",
        "пигментация",
        "уход",
        "ингредиент",
        "состав",
        "inci",
        "spf",
        "ретинол",
        "ниацинамид",
    }

    def validate_user_text(self, text: str) -> GuardrailResult:
        lowered = text.lower()

        if any(token in lowered for token in self._code_keywords) or any(
            pattern.search(text) for pattern in self._code_patterns
        ):
            return GuardrailResult(
                allowed=False,
                message=(
                    "Я работаю как AI косметолог Demi Results и помогаю с уходом за кожей. "
                    "По программированию не консультирую."
                ),
            )

        if any(token in lowered for token in self._offtopic_keywords) and not any(
            token in lowered for token in self._domain_keywords
        ):
            return GuardrailResult(
                allowed=False,
                message=(
                    "Мой фокус — уход за кожей и составы косметики. "
                    "Давайте вернемся к этой теме."
                ),
            )

        return GuardrailResult(allowed=True)

    def validate_model_response(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            raise EmptyResponseError("model returned empty content")
        if "```" in cleaned:
            raise GuardrailViolation("model returned code block")
        return clean_response(cleaned, fallback="Уточните запрос по уходу, и я помогу.")
