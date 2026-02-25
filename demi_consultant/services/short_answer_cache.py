from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from time import time


@dataclass(slots=True)
class _CacheValue:
    answer: str
    expires_at: float


class ShortAnswerCache:
    """Caches high-frequency answers to avoid unnecessary model calls."""

    def __init__(self, ttl_seconds: int = 6 * 60 * 60) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, _CacheValue] = {}
        self._templates = {
            "тип кожи жирная": (
                "Для жирной кожи обычно подходит мягкое гелевое очищение, "
                "легкий увлажняющий крем и ежедневный SPF. "
                "Добавляйте себорегулирующие активы постепенно и делайте патч-тест."
            ),
            "тип кожи сухая": (
                "Для сухой кожи важны мягкое очищение без пересушивания, "
                "крем с церамидами и SPF каждый день. "
                "Активы вводите постепенно и обязательно через патч-тест."
            ),
            "можно ли ретинол летом": (
                "Ретиноиды летом допустимы при вечернем применении и строгом SPF днем. "
                "Начинайте с низкой частоты, следите за барьером и делайте патч-тест."
            ),
            "нужен ли spf": (
                "SPF нужен ежедневно, даже в пасмурные дни. "
                "Для лица ориентируйтесь на SPF 30-50 и обновляйте защиту при длительном пребывании на улице."
            ),
        }

    def match(self, user_text: str) -> str | None:
        normalized = self._normalize(user_text)
        if not normalized:
            return None

        best_key = ""
        best_score = 0.0
        for key in self._templates:
            score = SequenceMatcher(None, normalized, key).ratio()
            if score > best_score:
                best_score = score
                best_key = key

        if best_score < 0.90 or not best_key:
            return None

        current = self._cache.get(best_key)
        now = time()
        if current and current.expires_at > now:
            return current.answer

        answer = self._templates[best_key]
        self._cache[best_key] = _CacheValue(answer=answer, expires_at=now + self._ttl_seconds)
        return answer

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.lower().split()).strip(".!?,:; ")
