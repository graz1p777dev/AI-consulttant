from __future__ import annotations

from dataclasses import dataclass

from demi_consultant.state.fsm import ChatMode


@dataclass(frozen=True)
class ContextSignals:
    sensitivity_risk: bool = False
    unrealistic_request: bool = False
    comparison_requested: bool = False


class ContextIntelligenceService:
    _sensitive_markers = (
        "жжет",
        "жжение",
        "сильное раздражение",
        "сыпь",
        "аллер",
        "болит",
        "кровит",
    )

    _unrealistic_markers = (
        "за 1 день",
        "мгновенно",
        "навсегда за сутки",
        "сразу убрать",
    )

    _comparison_markers = (
        "сравни",
        "разница",
        "лучше",
        "хуже",
        "прогресс",
    )

    def analyze(self, user_text: str, mode: ChatMode) -> ContextSignals:
        lowered = user_text.lower()
        return ContextSignals(
            sensitivity_risk=any(marker in lowered for marker in self._sensitive_markers),
            unrealistic_request=any(marker in lowered for marker in self._unrealistic_markers),
            comparison_requested=any(marker in lowered for marker in self._comparison_markers),
        )

    def build_runtime_guidance(self, signals: ContextSignals, mode: ChatMode) -> str:
        lines = [
            "Пишите уважительно и конкретно.",
            "Сохраняйте премиальный клинический тон без фамильярности.",
        ]

        if signals.unrealistic_request:
            lines.append("Мягко объясните реалистичные сроки и этапность ухода.")

        if signals.sensitivity_risk and mode != ChatMode.SKIN_TYPE:
            lines.append("Для реактивной кожи предлагайте максимально щадящий ввод активов.")

        if signals.comparison_requested:
            lines.append("Сравнивайте варианты коротко: плюсы, риски, кому подходит.")

        if mode == ChatMode.INGREDIENT_CHECK:
            lines.append("Форматируйте итог по блокам: безопасно, осторожно, нежелательно.")

        return "\n".join(lines)
