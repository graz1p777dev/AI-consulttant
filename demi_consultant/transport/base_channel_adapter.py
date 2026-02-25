from __future__ import annotations

from abc import ABC, abstractmethod


class BaseChannelAdapter(ABC):
    @abstractmethod
    async def handle_text(self, user_id: str, text: str, *, event_ts: float | None = None) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def handle_image(
        self,
        user_id: str,
        image_bytes: bytes,
        *,
        caption: str | None,
        image_mime_type: str,
        event_ts: float | None = None,
    ) -> str | None:
        raise NotImplementedError
