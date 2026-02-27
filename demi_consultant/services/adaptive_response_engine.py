from __future__ import annotations

from dataclasses import dataclass

from demi_consultant.services.intent_router import IntentResult
from demi_consultant.state.user_session import UserSession


@dataclass(slots=True, frozen=True)
class AdaptiveResponseProfile:
    short_mode: bool
    depth_level: str
    suppress_lecture: bool


class AdaptiveResponseEngine:
    """Adaptive short/deep mode selector for chat-like flow."""

    def choose(self, user_text: str, session: UserSession, intent: IntentResult) -> AdaptiveResponseProfile:
        normalized = user_text.strip()
        short_input = len(normalized) < 80

        fast_dialogue = False
        if len(session.message_timestamps) >= 4:
            last_four = list(session.message_timestamps)[-4:]
            fast_dialogue = (last_four[-1] - last_four[0]) <= 45

        if intent.intent_type == "follow_up":
            return AdaptiveResponseProfile(short_mode=True, depth_level="short", suppress_lecture=True)

        if short_input and intent.complexity == "simple":
            return AdaptiveResponseProfile(short_mode=True, depth_level="short", suppress_lecture=True)

        if intent.complexity == "deep" or len(normalized) > 180:
            return AdaptiveResponseProfile(short_mode=False, depth_level="deep", suppress_lecture=False)

        if intent.complexity == "medium" or session.total_messages_received >= 8:
            return AdaptiveResponseProfile(short_mode=fast_dialogue, depth_level="medium", suppress_lecture=fast_dialogue)

        return AdaptiveResponseProfile(short_mode=short_input or fast_dialogue, depth_level="short", suppress_lecture=short_input)
