from __future__ import annotations

from typing import Any

from demi_consultant.state.user_session import UserSession


class ConversionEngine:
    def __init__(self, conversion_rules: dict[str, Any], human_contact: str) -> None:
        keywords = conversion_rules.get("purchase_intent_keywords", [])
        self._keywords = [str(item).lower() for item in keywords if str(item).strip()]
        self._dialogue_trigger_messages = int(conversion_rules.get("dialogue_trigger_messages", 5))
        self._soft_offer_template = str(
            conversion_rules.get(
                "soft_offer_template",
                "Если хотите, я подберу категории средств под ваш бюджет и этап ухода.",
            )
        )
        self._human_handoff_template = str(
            conversion_rules.get(
                "human_handoff_template",
                "Могу передать диалог менеджеру для уточнения наличия и финального подбора.",
            )
        )
        self._human_contact = human_contact

    def detect_purchase_intent(self, text: str, *, user_message_count: int) -> bool:
        lowered = text.lower()
        keyword_hit = any(keyword in lowered for keyword in self._keywords)
        return keyword_hit or user_message_count >= self._dialogue_trigger_messages

    def build_soft_offer(self) -> str:
        return self._soft_offer_template

    def escalate_to_human(self) -> str:
        return f"Если удобно, подключу менеджера: {self._human_contact}. {self._human_handoff_template}"

    @property
    def dialogue_trigger_messages(self) -> int:
        return self._dialogue_trigger_messages

    def is_hot_lead(self, session: UserSession) -> bool:
        return session.purchase_stage == "hot_lead"
