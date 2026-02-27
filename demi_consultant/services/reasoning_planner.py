from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from demi_consultant.services.intent_router import IntentResult
from demi_consultant.state.user_session import UserSession

ResponseMode = Literal["empathetic", "diagnostic", "educational", "short_answer"]
ReactionType = Literal["question_reaction", "empathy", "validation", "neutral"]
DepthLevel = Literal["short", "medium", "deep"]
RiskLevel = Literal["low", "medium"]


@dataclass(slots=True, frozen=True)
class Plan:
    response_mode: ResponseMode
    reaction_type: ReactionType
    depth_level: DepthLevel
    need_clarification: bool
    risk_level: RiskLevel


class ReasoningPlanner:
    """Builds response plan from intent + memory-aware context."""

    def plan_response(self, intent: IntentResult, session: UserSession, context: dict[str, Any]) -> Plan:
        response_mode = self._response_mode(intent)
        reaction_type = self._reaction_type(intent)
        depth_level = self._depth_level(intent, session, context)
        need_clarification = self._need_clarification(intent, session, context)
        risk_level = self._risk_level(intent, session, context)

        last_assistant = next(
            (turn.content.lower() for turn in reversed(session.history) if turn.role == "assistant" and turn.content.strip()),
            "",
        )
        if last_assistant and response_mode != "short_answer" and "уточните" in last_assistant:
            need_clarification = False

        return Plan(
            response_mode=response_mode,
            reaction_type=reaction_type,
            depth_level=depth_level,
            need_clarification=need_clarification,
            risk_level=risk_level,
        )

    @staticmethod
    def _response_mode(intent: IntentResult) -> ResponseMode:
        if intent.intent_type == "follow_up":
            return "short_answer"
        if intent.intent_type in {"complaint", "emotion"}:
            return "empathetic"
        if intent.intent_type == "off_topic":
            return "short_answer"
        if intent.intent_type == "purchase":
            return "diagnostic"
        return "educational"

    @staticmethod
    def _reaction_type(intent: IntentResult) -> ReactionType:
        if intent.intent_type == "question":
            return "question_reaction"
        if intent.intent_type == "complaint":
            return "empathy"
        if intent.intent_type == "emotion":
            return "validation"
        if intent.intent_type == "follow_up":
            return "neutral"
        if intent.intent_type == "purchase":
            return "neutral"
        return "neutral"

    @staticmethod
    def _depth_level(intent: IntentResult, session: UserSession, context: dict[str, Any]) -> DepthLevel:
        if intent.intent_type == "follow_up":
            return "short"

        if context.get("simple_question"):
            return "short"

        if intent.complexity == "deep":
            return "deep"
        if intent.complexity == "medium":
            return "medium"

        if session.total_messages_received >= 10:
            return "medium"
        return "short"

    @staticmethod
    def _need_clarification(intent: IntentResult, session: UserSession, context: dict[str, Any]) -> bool:
        has_photo = bool(context.get("has_photo"))
        has_symptoms = bool(context.get("has_symptoms"))

        if has_photo:
            return False
        if intent.intent_type == "follow_up":
            return False
        if intent.confidence < 0.6:
            return True
        if intent.intent_type in {"question", "purchase"} and not has_symptoms and not session.concerns:
            return True
        return False

    @staticmethod
    def _risk_level(intent: IntentResult, session: UserSession, context: dict[str, Any]) -> RiskLevel:
        if context.get("sensitivity_risk"):
            return "medium"
        if intent.intent_type in {"complaint", "emotion"} and not context.get("has_photo"):
            return "medium"
        journal = session.skin_journal if isinstance(session.skin_journal, dict) else {}
        not_worked = journal.get("not_worked") if isinstance(journal, dict) else []
        if isinstance(not_worked, list) and not_worked:
            return "medium"
        return "low"
