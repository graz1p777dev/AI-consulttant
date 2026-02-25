from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from demi_consultant.core.exceptions import MetaAPIError

logger = logging.getLogger(__name__)


class MetaClient:
    """Meta Cloud API client for WhatsApp transport."""

    def __init__(
        self,
        *,
        api_version: str,
        phone_number_id: str,
        access_token: str,
        app_secret: str | None,
        timeout: float = 20.0,
    ) -> None:
        self._api_version = api_version
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._app_secret = app_secret
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._http.aclose()

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        if not self._app_secret:
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        actual_signature = signature_header.split("=", 1)[1]
        digest = hmac.new(
            self._app_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(digest, actual_signature)

    async def send_text(self, user_id: str, text: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": user_id,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        await self._post_json(
            f"/{self._api_version}/{self._phone_number_id}/messages",
            payload,
        )

    async def send_typing(self, user_id: str) -> None:
        # WhatsApp Cloud API has no universal typing endpoint; keep hook for symmetry.
        logger.debug("Typing placeholder used for WhatsApp user %s", user_id)

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        media_meta = await self._get_json(f"/{self._api_version}/{media_id}")
        media_url = str(media_meta.get("url", ""))
        mime_type = str(media_meta.get("mime_type", "application/octet-stream"))
        if not media_url:
            raise MetaAPIError("Meta media URL is missing")

        response = await self._http.get(
            media_url,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        if response.status_code >= 400:
            raise MetaAPIError(f"Meta media download failed: {response.status_code} {response.text[:200]}")
        return response.content, mime_type

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._http.post(
            f"https://graph.facebook.com{path}",
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if response.status_code >= 400:
            raise MetaAPIError(f"Meta API POST failed: {response.status_code} {response.text[:300]}")
        return response.json()

    async def _get_json(self, path: str) -> dict[str, Any]:
        response = await self._http.get(
            f"https://graph.facebook.com{path}",
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        if response.status_code >= 400:
            raise MetaAPIError(f"Meta API GET failed: {response.status_code} {response.text[:300]}")
        data = response.json()
        if not isinstance(data, dict):
            raise MetaAPIError("Meta API returned non-object payload")
        return data
