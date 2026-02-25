from __future__ import annotations

from demi_consultant.state.user_session import DialogueTurn, UserSession
from demi_consultant.utils.text_utils import compact_text


class TokenGuard:
    """Approximate token budget control for dialogue context."""

    _low_value_messages = {
        "ok",
        "ок",
        "понял",
        "поняла",
        "понятно",
        "спасибо",
        "thanks",
        "thank you",
    }

    def __init__(self, *, max_context_tokens: int = 3000, keep_messages: int = 6) -> None:
        self._max_context_tokens = max_context_tokens
        self._keep_messages = keep_messages

    def trim_history(self, history: list[DialogueTurn], session: UserSession) -> list[DialogueTurn]:
        if not history:
            return []

        filtered = [
            turn
            for turn in history
            if not self._is_small_talk(turn)
        ]
        if not filtered:
            filtered = history[-self._keep_messages :]

        if self._estimate_tokens(filtered) <= self._max_context_tokens:
            return [
                DialogueTurn(role=turn.role, content=compact_text(turn.content, max_chars=900))
                for turn in filtered
            ]

        # Priority: recent turns first.
        trimmed = filtered[-self._keep_messages :]
        while len(trimmed) > 2 and self._estimate_tokens(trimmed) > self._max_context_tokens:
            trimmed = trimmed[1:]

        if self._estimate_tokens(trimmed) > self._max_context_tokens:
            compacted: list[DialogueTurn] = []
            for turn in trimmed:
                compacted.append(
                    DialogueTurn(role=turn.role, content=compact_text(turn.content, max_chars=350))
                )
            trimmed = compacted

        return trimmed

    def _estimate_tokens(self, history: list[DialogueTurn]) -> int:
        total_chars = sum(len(turn.content) for turn in history)
        # Approximation: ~4 chars per token for mixed RU/EN text.
        return max(1, total_chars // 4)

    def _is_small_talk(self, turn: DialogueTurn) -> bool:
        normalized = " ".join(turn.content.lower().split()).strip(".!?,:; ")
        return normalized in self._low_value_messages
