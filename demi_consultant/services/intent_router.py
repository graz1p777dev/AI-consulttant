from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Literal

from demi_consultant.ai.openai_client import OpenAIClient
from demi_consultant.state.user_session import DialogueTurn

IntentType = Literal["question", "complaint", "emotion", "follow_up", "purchase", "off_topic"]
EmotionalTone = Literal["neutral", "worried", "confused", "frustrated"]
Complexity = Literal["simple", "medium", "deep"]


@dataclass(slots=True, frozen=True)
class IntentResult:
    intent_type: IntentType
    confidence: float
    emotional_tone: EmotionalTone
    complexity: Complexity


class IntentRouter:
    """Classifies user intent with lightweight LLM call and heuristic fallback."""

    _OFFTOPIC_MARKERS: tuple[str, ...] = (
        "python",
        "javascript",
        "код",
        "программ",
        "полит",
        "философ",
        "спорт",
        "погода",
        "новости",
        "компьют",
        "pc",
        "ноутбук",
    )
    _PURCHASE_MARKERS: tuple[str, ...] = (
        "купить",
        "цена",
        "стоимость",
        "в наличии",
        "заказать",
        "менеджер",
        "косметолог магазина",
    )
    _EMOTION_MARKERS: tuple[str, ...] = (
        "пережива",
        "боюсь",
        "тревож",
        "волную",
        "расстро",
        "пуга",
    )
    _COMPLAINT_MARKERS: tuple[str, ...] = (
        "сух",
        "жир",
        "прыщ",
        "акне",
        "шелуш",
        "стяг",
        "раздраж",
        "красн",
        "чеш",
        "жжет",
        "шерша",
    )
    _FOLLOW_UP_MARKERS: tuple[str, ...] = (
        "давай",
        "ок",
        "окей",
        "а если",
        "и если",
        "дальше",
        "угу",
        "понял",
    )
    _QUESTION_MARKERS: tuple[str, ...] = (
        "как",
        "что",
        "почему",
        "можно",
        "нужно",
        "какие",
        "какой",
    )

    def __init__(self, openai_client: OpenAIClient, *, enabled: bool = True) -> None:
        self._openai_client = openai_client
        self._enabled = enabled

    async def classify_intent(
        self,
        user_text: str,
        history: list[DialogueTurn] | list[dict[str, str]] | None = None,
    ) -> IntentResult:
        if not self._enabled:
            return self._heuristic_intent(user_text)

        llm_result = await self._classify_with_llm(user_text, history)
        if llm_result is not None:
            return llm_result
        return self._heuristic_intent(user_text)

    async def _classify_with_llm(
        self,
        user_text: str,
        history: list[DialogueTurn] | list[dict[str, str]] | None,
    ) -> IntentResult | None:
        history_tail = self._history_tail(history)
        payload = {
            "user_text": user_text,
            "history_tail": history_tail,
            "schema": {
                "intent_type": ["question", "complaint", "emotion", "follow_up", "purchase", "off_topic"],
                "confidence": "0..1",
                "emotional_tone": ["neutral", "worried", "confused", "frustrated"],
                "complexity": ["simple", "medium", "deep"],
            },
        }
        prompt = (
            "Классифицируй реплику пользователя для skincare-бота. "
            "Верни только JSON без пояснений."
        )

        try:
            raw = await self._openai_client.generate_reply(
                system_prompt=(
                    "Ты Intent Classifier. Верни строго JSON. "
                    "Без markdown, без текста вокруг."
                ),
                dialogue=[
                    {"role": "user", "content": f"{prompt}\n\n{json.dumps(payload, ensure_ascii=False)}"},
                ],
                max_output_tokens=120,
                verbosity="low",
                allow_small_output=True,
            )
        except Exception:
            return None

        return self._parse_llm_output(raw)

    def _parse_llm_output(self, raw: str) -> IntentResult | None:
        if not raw:
            return None

        candidate = raw.strip()
        match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if match:
            candidate = match.group(0)

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return None

        intent_type = self._normalize_intent(data.get("intent_type"))
        emotional_tone = self._normalize_tone(data.get("emotional_tone"))
        complexity = self._normalize_complexity(data.get("complexity"))
        confidence = self._clamp_confidence(data.get("confidence"), fallback=0.65)

        if intent_type is None or emotional_tone is None or complexity is None:
            return None

        return IntentResult(
            intent_type=intent_type,
            confidence=confidence,
            emotional_tone=emotional_tone,
            complexity=complexity,
        )

    def _heuristic_intent(self, user_text: str) -> IntentResult:
        lowered = user_text.lower().strip()
        tokens = lowered.split()

        if any(marker in lowered for marker in self._OFFTOPIC_MARKERS):
            return IntentResult("off_topic", 0.9, "neutral", self._heuristic_complexity(user_text))

        if any(marker in lowered for marker in self._PURCHASE_MARKERS):
            return IntentResult("purchase", 0.86, "neutral", self._heuristic_complexity(user_text))

        if len(lowered) <= 26 and any(lowered.startswith(marker) for marker in self._FOLLOW_UP_MARKERS):
            return IntentResult("follow_up", 0.88, self._heuristic_tone(lowered), "simple")

        if "?" in user_text or (tokens and tokens[0] in self._QUESTION_MARKERS):
            return IntentResult("question", 0.82, self._heuristic_tone(lowered), self._heuristic_complexity(user_text))

        if any(marker in lowered for marker in self._EMOTION_MARKERS):
            return IntentResult("emotion", 0.78, self._heuristic_tone(lowered), self._heuristic_complexity(user_text))

        if any(marker in lowered for marker in self._COMPLAINT_MARKERS):
            return IntentResult("complaint", 0.8, self._heuristic_tone(lowered), self._heuristic_complexity(user_text))

        return IntentResult("question", 0.56, self._heuristic_tone(lowered), self._heuristic_complexity(user_text))

    @staticmethod
    def _history_tail(history: list[DialogueTurn] | list[dict[str, str]] | None) -> list[dict[str, str]]:
        if not history:
            return []
        tail = history[-4:]
        normalized: list[dict[str, str]] = []
        for item in tail:
            if isinstance(item, DialogueTurn):
                normalized.append({"role": item.role, "content": item.content[:180]})
                continue
            if isinstance(item, dict):
                role = str(item.get("role", "user"))
                content = str(item.get("content", ""))
                normalized.append({"role": role, "content": content[:180]})
        return normalized

    @staticmethod
    def _clamp_confidence(value: Any, *, fallback: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(confidence, 1.0))

    @staticmethod
    def _normalize_intent(value: Any) -> IntentType | None:
        allowed = {"question", "complaint", "emotion", "follow_up", "purchase", "off_topic"}
        normalized = str(value or "").strip().lower()
        if normalized in allowed:
            return normalized  # type: ignore[return-value]
        return None

    @staticmethod
    def _normalize_tone(value: Any) -> EmotionalTone | None:
        allowed = {"neutral", "worried", "confused", "frustrated"}
        normalized = str(value or "").strip().lower()
        if normalized in allowed:
            return normalized  # type: ignore[return-value]
        return None

    @staticmethod
    def _normalize_complexity(value: Any) -> Complexity | None:
        allowed = {"simple", "medium", "deep"}
        normalized = str(value or "").strip().lower()
        if normalized in allowed:
            return normalized  # type: ignore[return-value]
        return None

    def _heuristic_tone(self, lowered: str) -> EmotionalTone:
        if any(marker in lowered for marker in ("боюсь", "трев", "пережива", "настораж")):
            return "worried"
        if any(marker in lowered for marker in ("не понимаю", "запутал", "неясно", "как это")):
            return "confused"
        if any(marker in lowered for marker in ("надоело", "бесит", "не помогает", "устал")):
            return "frustrated"
        return "neutral"

    @staticmethod
    def _heuristic_complexity(user_text: str) -> Complexity:
        length = len(user_text.strip())
        if length > 180 or user_text.count("?") > 1:
            return "deep"
        if length > 80:
            return "medium"
        return "simple"
