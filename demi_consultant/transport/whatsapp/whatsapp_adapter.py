from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from demi_consultant.core.config import Settings
from demi_consultant.core.exceptions import MetaAPIError, PayloadValidationError
from demi_consultant.core.logger import log_extra
from demi_consultant.integrations.meta_api.meta_client import MetaClient
from demi_consultant.services.consultation_service import ConsultationService
from demi_consultant.transport.base_channel_adapter import BaseChannelAdapter
from demi_consultant.transport.meta.message_normalizer import normalize_whatsapp_payload

logger = logging.getLogger(__name__)


class WhatsAppAdapter(BaseChannelAdapter):
    def __init__(
        self,
        *,
        settings: Settings,
        consultation_service: ConsultationService,
        meta_client: MetaClient,
    ) -> None:
        self._settings = settings
        self._consultation_service = consultation_service
        self._meta_client = meta_client
        self.app = FastAPI(title="Demi Consultant WhatsApp Webhook")
        self._register_routes()

    async def handle_text(self, user_id: str, text: str, *, event_ts: float | None = None) -> str | None:
        return await self._consultation_service.process_message(
            user_id=user_id,
            text=text,
            channel="whatsapp",
            event_ts=event_ts,
        )

    async def handle_image(
        self,
        user_id: str,
        image_bytes: bytes,
        *,
        caption: str | None,
        image_mime_type: str,
        event_ts: float | None = None,
    ) -> str | None:
        return await self._consultation_service.process_photo(
            user_id=user_id,
            image_bytes=image_bytes,
            caption=caption,
            channel="whatsapp",
            image_mime_type=image_mime_type,
            event_ts=event_ts,
        )

    def _register_routes(self) -> None:
        @self.app.get("/webhook")
        async def verify_webhook(request: Request) -> PlainTextResponse:
            mode = request.query_params.get("hub.mode")
            verify_token = request.query_params.get("hub.verify_token")
            challenge = request.query_params.get("hub.challenge", "")

            if mode == "subscribe" and verify_token == self._settings.whatsapp_verify_token:
                return PlainTextResponse(challenge)
            raise HTTPException(status_code=403, detail="Webhook verification failed")

        @self.app.post("/webhook")
        async def receive_webhook(request: Request) -> JSONResponse:
            raw_body = await request.body()
            signature = request.headers.get("X-Hub-Signature-256")
            if not self._meta_client.verify_signature(raw_body, signature):
                raise HTTPException(status_code=403, detail="Invalid webhook signature")

            try:
                payload: dict[str, Any] = await request.json()
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Malformed JSON payload") from exc

            try:
                messages = normalize_whatsapp_payload(payload)
            except PayloadValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            if not messages:
                return JSONResponse({"status": "ignored"})

            for message in messages:
                try:
                    await self._meta_client.send_typing(message.user_id)

                    if message.text is not None and message.text.strip():
                        reply = await self.handle_text(message.user_id, message.text)
                    elif message.media_id:
                        image_bytes, mime_type = await self._meta_client.download_media(message.media_id)
                        reply = await self.handle_image(
                            message.user_id,
                            image_bytes,
                            caption=message.caption,
                            image_mime_type=message.mime_type or mime_type,
                        )
                    else:
                        reply = None

                    if reply:
                        await self._meta_client.send_text(message.user_id, reply)
                except MetaAPIError as exc:
                    logger.warning(
                        "WhatsApp Meta API error: %s",
                        exc,
                        extra=log_extra(channel="whatsapp", user_id=message.user_id),
                    )
                    try:
                        await self._meta_client.send_text(
                            message.user_id,
                            "Вижу техническую ошибку. Попробуйте через минуту.",
                        )
                    except Exception:
                        logger.exception(
                            "Failed to deliver WhatsApp fallback message",
                            extra=log_extra(channel="whatsapp", user_id=message.user_id),
                        )
                except Exception as exc:  # pragma: no cover - transport safety net
                    logger.exception(
                        "WhatsApp webhook processing failed: %s",
                        exc,
                        extra=log_extra(channel="whatsapp", user_id=message.user_id),
                    )

            return JSONResponse({"status": "ok"})
