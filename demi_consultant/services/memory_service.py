from __future__ import annotations

import threading

from demi_consultant.state.user_session import DialogueTurn, UserSession


class MemoryService:
    """In-memory user sessions and short dialogue context."""

    def __init__(self, max_history_messages: int = 16) -> None:
        self._sessions: dict[str, UserSession] = {}
        self._max_history_messages = max_history_messages
        self._lock = threading.Lock()

    def get_or_create_session(self, user_id: str) -> UserSession:
        with self._lock:
            session = self._sessions.get(user_id)
            if session is None:
                session = UserSession(user_id=user_id)
                self._sessions[user_id] = session
            return session

    def remember_user_message(self, user_id: str, text: str) -> UserSession:
        session = self.get_or_create_session(user_id)
        session.add_user_message(text)
        self._trim_history(session)
        return session

    def remember_assistant_message(self, user_id: str, text: str) -> UserSession:
        session = self.get_or_create_session(user_id)
        session.add_assistant_message(text)
        self._trim_history(session)
        return session

    def get_context_history(self, user_id: str) -> list[DialogueTurn]:
        return list(self.get_or_create_session(user_id).history)

    def count_user_messages(self, user_id: str) -> int:
        session = self.get_or_create_session(user_id)
        return sum(1 for turn in session.history if turn.role == "user")

    def _trim_history(self, session: UserSession) -> None:
        if len(session.history) <= self._max_history_messages:
            return
        session.history = session.history[-self._max_history_messages :]
