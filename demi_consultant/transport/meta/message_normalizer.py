from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from demi_consultant.core.exceptions import PayloadValidationError


@dataclass(slots=True)
class NormalizedMessage:
    user_id: str
    text: str | None = None
    image_bytes: bytes | None = None
    caption: str | None = None
    media_kind: str | None = None
    media_id: str | None = None
    media_url: str | None = None
    mime_type: str | None = None


def normalize_whatsapp_payload(payload: dict[str, Any]) -> list[NormalizedMessage]:
    if not isinstance(payload, dict):
        raise PayloadValidationError("WhatsApp payload must be a JSON object")

    result: list[NormalizedMessage] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return result

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            messages = value.get("messages")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, dict):
                    continue
                user_id = str(message.get("from", "")).strip()
                if not user_id:
                    continue
                message_type = str(message.get("type", "")).strip()

                if message_type == "text":
                    text_obj = message.get("text")
                    text = ""
                    if isinstance(text_obj, dict):
                        text = str(text_obj.get("body", "")).strip()
                    result.append(NormalizedMessage(user_id=user_id, text=text))
                    continue

                if message_type == "image":
                    image_obj = message.get("image")
                    if not isinstance(image_obj, dict):
                        continue
                    result.append(
                        NormalizedMessage(
                            user_id=user_id,
                            caption=str(image_obj.get("caption", "")).strip() or None,
                            media_kind="image",
                            media_id=str(image_obj.get("id", "")).strip() or None,
                            mime_type=str(image_obj.get("mime_type", "")).strip() or None,
                        )
                    )
                    continue

                if message_type == "audio":
                    audio_obj = message.get("audio")
                    if not isinstance(audio_obj, dict):
                        continue
                    result.append(
                        NormalizedMessage(
                            user_id=user_id,
                            media_kind="audio",
                            media_id=str(audio_obj.get("id", "")).strip() or None,
                            mime_type=str(audio_obj.get("mime_type", "")).strip() or None,
                        )
                    )
                    continue

    return result


def normalize_instagram_payload(payload: dict[str, Any]) -> list[NormalizedMessage]:
    if not isinstance(payload, dict):
        raise PayloadValidationError("Instagram payload must be a JSON object")

    result: list[NormalizedMessage] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return result

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        messaging = entry.get("messaging")
        if isinstance(messaging, list):
            for event in messaging:
                _normalize_instagram_event(event, result)
            continue

        # Some setups place messages inside "changes" payloads.
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            event = {
                "sender": {"id": value.get("from")},
                "message": value.get("message") or value,
            }
            _normalize_instagram_event(event, result)

    return result


def _normalize_instagram_event(event: Any, out: list[NormalizedMessage]) -> None:
    if not isinstance(event, dict):
        return

    sender = event.get("sender")
    if not isinstance(sender, dict):
        return
    user_id = str(sender.get("id", "")).strip()
    if not user_id:
        return

    message = event.get("message")
    if not isinstance(message, dict):
        return

    text = str(message.get("text", "")).strip()
    if text:
        out.append(NormalizedMessage(user_id=user_id, text=text))
        return

    attachments = message.get("attachments")
    if not isinstance(attachments, list):
        return

    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_type = str(attachment.get("type", "")).strip().lower()
        if attachment_type not in {"image", "audio"}:
            continue
        payload = attachment.get("payload")
        if not isinstance(payload, dict):
            continue

        out.append(
            NormalizedMessage(
                user_id=user_id,
                caption=str(payload.get("title", "")).strip() or None,
                media_kind=attachment_type,
                media_id=str(payload.get("id", "")).strip() or None,
                media_url=str(payload.get("url", "")).strip() or None,
            )
        )
