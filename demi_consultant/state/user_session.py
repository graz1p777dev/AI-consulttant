from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import time
from typing import Any, Literal

from demi_consultant.state.fsm import ChatMode

Role = Literal["user", "assistant"]
OnboardingStep = Literal["name", "age", "done"]


@dataclass(slots=True)
class DialogueTurn:
    role: Role
    content: str


@dataclass(slots=True)
class PhotoSnapshot:
    image_bytes: bytes
    mime_type: str
    caption: str | None = None
    created_at: float = field(default_factory=time)


@dataclass(slots=True)
class UserSession:
    user_id: str
    mode: ChatMode = ChatMode.CHAT

    name: str | None = None
    age: int | None = None
    age_range: str | None = None
    onboarding_completed: bool = False
    onboarding_step: OnboardingStep | None = None
    onboarding_attempts: int = 0

    menu_shown_once: bool = False
    menu_active: bool = False

    consultation_started: bool = False
    skin_type: str | None = None
    skin_type_confidence: float | None = None
    concerns: str | None = None
    allergies: str | None = None
    last_recommendations: list[str] = field(default_factory=list)
    purchase_stage: str | None = None
    skin_journal: dict[str, Any] = field(
        default_factory=lambda: {
            "skin_type": None,
            "reactions": [],
            "worked": [],
            "not_worked": [],
        }
    )

    waiting_for_photo: bool = False
    history: list[DialogueTurn] = field(default_factory=list)
    progress_photos: list[PhotoSnapshot] = field(default_factory=list)

    last_message_text: str | None = None
    repeated_count: int = 0
    muted_until: float = 0.0
    blocked_until: float = 0.0
    message_timestamps: deque[float] = field(default_factory=deque)
    total_messages_received: int = 0
    last_image_at: float = 0.0
    images_in_session: int = 0

    def add_user_message(self, text: str) -> None:
        self.history.append(DialogueTurn(role="user", content=text))

    def add_assistant_message(self, text: str) -> None:
        self.history.append(DialogueTurn(role="assistant", content=text))

    def set_mode(self, mode: ChatMode) -> None:
        self.mode = mode

    def add_progress_photo(self, image_bytes: bytes, mime_type: str, caption: str | None = None) -> None:
        self.progress_photos.append(
            PhotoSnapshot(
                image_bytes=image_bytes,
                mime_type=mime_type,
                caption=caption,
            )
        )
        if len(self.progress_photos) > 12:
            self.progress_photos = self.progress_photos[-12:]

    def get_skin_history(self) -> list[PhotoSnapshot]:
        return list(self.progress_photos)

    def register_message(self, ts: float, *, window_seconds: int) -> int:
        self.total_messages_received += 1
        self.message_timestamps.append(ts)
        cutoff = ts - window_seconds
        while self.message_timestamps and self.message_timestamps[0] < cutoff:
            self.message_timestamps.popleft()
        return len(self.message_timestamps)

    def track_repeat(self, normalized_text: str) -> int:
        if self.last_message_text == normalized_text:
            self.repeated_count += 1
        else:
            self.last_message_text = normalized_text
            self.repeated_count = 1
        return self.repeated_count

    def register_image(self, ts: float) -> None:
        self.last_image_at = ts
        self.images_in_session += 1

    def reset_onboarding(self) -> None:
        self.name = None
        self.age = None
        self.age_range = None
        self.onboarding_completed = False
        self.onboarding_step = "name"
        self.onboarding_attempts = 0
        self.menu_shown_once = False
        self.menu_active = False

        self.mode = ChatMode.CHAT
        self.waiting_for_photo = False

        self.last_message_text = None
        self.repeated_count = 0
        self.muted_until = 0.0
        self.blocked_until = 0.0
        self.message_timestamps.clear()
        self.total_messages_received = 0
        self.skin_journal = {
            "skin_type": None,
            "reactions": [],
            "worked": [],
            "not_worked": [],
        }
