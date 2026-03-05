from __future__ import annotations

import base64
import logging
import re

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from demi_consultant.core.config import Settings
from demi_consultant.core.logger import log_extra
from demi_consultant.services.consultation_service import ConsultationService
from demi_consultant.services.localization import text as tr

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=6000)
    channel: str = Field(default="api", min_length=1, max_length=40)
    model_name_override: str | None = Field(default=None, max_length=120)


class AudioChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    audio_base64: str = Field(min_length=1)
    mime_type: str | None = Field(default=None, max_length=120)
    file_name: str | None = Field(default=None, max_length=255)
    channel: str = Field(default="api", min_length=1, max_length=40)
    model_name_override: str | None = Field(default=None, max_length=120)


class ChatResponse(BaseModel):
    ok: bool
    reply: str | None = None
    transcript: str | None = None


class HTTPAPIAdapter:
    _CHANNEL_PATTERN = re.compile(r"^[a-z0-9_-]{1,40}$")

    def __init__(
        self,
        *,
        settings: Settings,
        consultation_service: ConsultationService,
    ) -> None:
        self._settings = settings
        self._consultation_service = consultation_service
        self.app = FastAPI(title="Demi Consultant HTTP API")
        self._register_routes()

    def _check_auth(self, authorization: str | None) -> None:
        token = self._settings.api_bearer_token
        if not token:
            return
        expected = f"Bearer {token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @classmethod
    def _sanitize_channel(cls, channel: str) -> str:
        normalized = channel.strip().lower()
        if cls._CHANNEL_PATTERN.fullmatch(normalized):
            return normalized
        return "api"

    def _register_routes(self) -> None:
        @self.app.get("/healthz")
        async def healthz() -> dict[str, str]:
            return {"status": "ok"}

        @self.app.post("/api/chat", response_model=ChatResponse)
        async def chat(
            payload: ChatRequest,
            authorization: str | None = Header(default=None, alias="Authorization"),
        ) -> ChatResponse:
            self._check_auth(authorization)
            channel = self._sanitize_channel(payload.channel)

            try:
                reply = await self._consultation_service.process_message(
                    user_id=payload.user_id,
                    text=payload.text,
                    channel=channel,
                    model_name_override=payload.model_name_override,
                )
            except Exception as exc:  # pragma: no cover - transport safety net
                logger.exception(
                    "HTTP API text handling failed: %s",
                    exc,
                    extra=log_extra(channel=channel, user_id=payload.user_id),
                )
                session = self._consultation_service.get_session(payload.user_id)
                return ChatResponse(ok=True, reply=tr("technical_error", session.language))

            return ChatResponse(ok=True, reply=reply)

        @self.app.post("/api/chat/audio", response_model=ChatResponse)
        async def chat_audio(
            payload: AudioChatRequest,
            authorization: str | None = Header(default=None, alias="Authorization"),
        ) -> ChatResponse:
            self._check_auth(authorization)
            channel = self._sanitize_channel(payload.channel)
            session = self._consultation_service.get_session(payload.user_id)

            try:
                audio_bytes = base64.b64decode(payload.audio_base64, validate=True)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Invalid audio_base64 payload") from exc
            if not audio_bytes:
                raise HTTPException(status_code=400, detail="Audio payload is empty")

            file_name = payload.file_name or "audio_message.ogg"
            model_override = payload.model_name_override or self._settings.voice_reply_model

            try:
                transcript = await self._consultation_service.transcribe_audio(
                    audio_bytes=audio_bytes,
                    file_name=file_name,
                    mime_type=payload.mime_type,
                    language=session.language,
                )
                transcript = transcript.strip()
                if not transcript:
                    return ChatResponse(ok=True, reply=tr("meaningless", session.language), transcript="")

                reply = await self._consultation_service.process_message(
                    user_id=payload.user_id,
                    text=transcript,
                    channel=channel,
                    model_name_override=model_override,
                )
            except Exception as exc:  # pragma: no cover - transport safety net
                logger.exception(
                    "HTTP API audio handling failed: %s",
                    exc,
                    extra=log_extra(channel=channel, user_id=payload.user_id),
                )
                return ChatResponse(ok=True, reply=tr("technical_error", session.language))

            return ChatResponse(ok=True, reply=reply, transcript=transcript)
