from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from openai import AsyncOpenAI

from demi_consultant.core.config import Settings
from demi_consultant.core.exceptions import AIClientError

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Resilient wrapper for OpenAI Responses API with retries."""

    _MIN_OUTPUT_LIMIT = 350
    _MAX_CONTINUATION_PASSES = 6
    _CONTINUATION_PROMPT = "Continue from where the reply was cut off. Do not repeat prior text."

    def __init__(self, settings: Settings, retries: int = 2) -> None:
        self._settings = settings
        self._retries = retries
        self._temperature_supported: bool | None = None
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.request_timeout_seconds,
        )

    async def generate_reply(
        self,
        *,
        system_prompt: str,
        dialogue: list[dict[str, str]],
        model_name: str | None = None,
        max_output_tokens: int | None = None,
        verbosity: str | None = None,
        allow_small_output: bool = False,
    ) -> str:
        selected_model = (model_name or self._settings.model_name).strip() or self._settings.model_name
        output_limit = max_output_tokens or self._settings.openai_max_output_tokens
        if not allow_small_output:
            output_limit = max(output_limit, self._MIN_OUTPUT_LIMIT)
        last_error: Exception | None = None

        for attempt in range(1, self._retries + 2):
            try:
                text, truncated = await self._request_text(
                    system_prompt=system_prompt,
                    dialogue=dialogue,
                    model_name=selected_model,
                    output_limit=output_limit,
                    verbosity=verbosity,
                )
                if text and truncated:
                    merged_text = text
                    still_truncated = truncated
                    continuation_passes = 0
                    while still_truncated and continuation_passes < self._MAX_CONTINUATION_PASSES:
                        continuation_passes += 1
                        continuation, still_truncated = await self._request_text(
                            system_prompt=system_prompt,
                            dialogue=[
                                *dialogue,
                                {"role": "assistant", "content": merged_text},
                                {"role": "user", "content": self._CONTINUATION_PROMPT},
                            ],
                            model_name=selected_model,
                            output_limit=output_limit,
                            verbosity=verbosity or "low",
                        )
                        if not continuation:
                            break
                        merged_text = self._merge_text_fragments(merged_text, continuation)
                    text = merged_text
                if text:
                    return text

                last_error = AIClientError("model returned no message text")
                logger.warning("OpenAI text attempt %s returned empty text", attempt)
            except Exception as exc:
                last_error = exc
                logger.warning("OpenAI text attempt %s failed: %s", attempt, exc)

            if attempt <= self._retries:
                await asyncio.sleep(0.7 * attempt)

        raise AIClientError("OpenAI retries exhausted") from last_error

    async def generate_reply_with_image(
        self,
        *,
        system_prompt: str,
        dialogue: list[dict[str, str]],
        image_bytes: bytes,
        image_mime_type: str,
        image_caption: str,
        model_name: str | None = None,
        max_output_tokens: int | None = None,
        verbosity: str | None = None,
        allow_small_output: bool = False,
    ) -> str:
        return await self.generate_reply_with_images(
            system_prompt=system_prompt,
            dialogue=dialogue,
            images=[(image_bytes, image_mime_type)],
            user_text=image_caption,
            model_name=model_name,
            max_output_tokens=max_output_tokens,
            verbosity=verbosity,
            allow_small_output=allow_small_output,
        )

    async def generate_reply_with_images(
        self,
        *,
        system_prompt: str,
        dialogue: list[dict[str, str]],
        images: list[tuple[bytes, str]],
        user_text: str,
        model_name: str | None = None,
        max_output_tokens: int | None = None,
        verbosity: str | None = None,
        allow_small_output: bool = False,
    ) -> str:
        selected_model = (model_name or self._settings.model_name).strip() or self._settings.model_name
        output_limit = max_output_tokens or self._settings.openai_max_output_tokens
        if not allow_small_output:
            output_limit = max(output_limit, self._MIN_OUTPUT_LIMIT)
        image_blocks = [self._image_block(image_bytes, mime_type) for image_bytes, mime_type in images]

        last_error: Exception | None = None
        for attempt in range(1, self._retries + 2):
            try:
                text, truncated = await self._request_vision_text(
                    system_prompt=system_prompt,
                    dialogue=dialogue,
                    image_blocks=image_blocks,
                    caption=user_text,
                    model_name=selected_model,
                    output_limit=output_limit,
                    verbosity=verbosity,
                )
                if text and truncated:
                    merged_text = text
                    still_truncated = truncated
                    continuation_passes = 0
                    while still_truncated and continuation_passes < self._MAX_CONTINUATION_PASSES:
                        continuation_passes += 1
                        continuation, still_truncated = await self._request_vision_text(
                            system_prompt=system_prompt,
                            dialogue=[
                                *dialogue,
                                {"role": "assistant", "content": merged_text},
                                {"role": "user", "content": self._CONTINUATION_PROMPT},
                            ],
                            image_blocks=image_blocks,
                            caption=user_text,
                            model_name=selected_model,
                            output_limit=output_limit,
                            verbosity=verbosity or "low",
                        )
                        if not continuation:
                            break
                        merged_text = self._merge_text_fragments(merged_text, continuation)
                    text = merged_text
                if text:
                    return text

                last_error = AIClientError("OpenAI image response is empty")
                logger.warning("OpenAI image attempt %s returned empty text", attempt)
            except Exception as exc:
                last_error = exc
                logger.warning("OpenAI image attempt %s failed: %s", attempt, exc)

            if attempt <= self._retries:
                await asyncio.sleep(0.7 * attempt)

        raise AIClientError("OpenAI image retries exhausted") from last_error

    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        mime_type: str | None = None,
        language: str | None = None,
    ) -> str:
        if not audio_bytes:
            raise AIClientError("audio payload is empty")

        file_payload: tuple[str, bytes] | tuple[str, bytes, str]
        if mime_type:
            file_payload = (file_name, audio_bytes, mime_type)
        else:
            file_payload = (file_name, audio_bytes)

        payload: dict[str, Any] = {
            "model": self._settings.audio_transcribe_model,
            "file": file_payload,
        }

        normalized_language = (language or "").strip().lower()
        language_map = {"ru": "ru", "en": "en", "kg": "ky"}
        transcription_language = language_map.get(normalized_language)
        if transcription_language:
            payload["language"] = transcription_language

        last_error: Exception | None = None
        for attempt in range(1, self._retries + 2):
            try:
                transcription = await self._client.audio.transcriptions.create(**payload)
                text = self._extract_transcription_text(transcription)
                if text:
                    return text

                last_error = AIClientError("audio transcription is empty")
                logger.warning("OpenAI audio transcription attempt %s returned empty text", attempt)
            except Exception as exc:
                last_error = exc
                logger.warning("OpenAI audio transcription attempt %s failed: %s", attempt, exc)

            if attempt <= self._retries:
                await asyncio.sleep(0.7 * attempt)

        raise AIClientError("OpenAI audio transcription retries exhausted") from last_error

    def _image_block(self, image_bytes: bytes, image_mime_type: str) -> dict[str, str]:
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        image_url = f"data:{image_mime_type};base64,{encoded_image}"
        return {"type": "input_image", "image_url": image_url}

    async def _request_text(
        self,
        *,
        system_prompt: str,
        dialogue: list[dict[str, str]],
        model_name: str,
        output_limit: int,
        verbosity: str | None,
    ) -> tuple[str, bool]:
        payload: dict[str, Any] = {
            "model": model_name,
            "max_output_tokens": output_limit,
            "input": [{"role": "system", "content": system_prompt}, *dialogue],
            **self._reasoning_params(model_name, verbosity),
        }
        if self._temperature_supported is not False:
            payload["temperature"] = 0.5

        response = await self._create_response(payload)
        return self._extract_text(response), self._is_truncated(response)

    async def _request_vision_text(
        self,
        *,
        system_prompt: str,
        dialogue: list[dict[str, str]],
        image_blocks: list[dict[str, str]],
        caption: str,
        model_name: str,
        output_limit: int,
        verbosity: str | None,
    ) -> tuple[str, bool]:
        payload: dict[str, Any] = {
            "model": model_name,
            "max_output_tokens": output_limit,
            "input": [
                {"role": "system", "content": system_prompt},
                *dialogue,
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": caption},
                        *image_blocks,
                    ],
                },
            ],
            **self._reasoning_params(model_name, verbosity),
        }
        if self._temperature_supported is not False:
            payload["temperature"] = 0.5

        response = await self._create_response(payload)
        return self._extract_text(response), self._is_truncated(response)

    async def _create_response(self, payload: dict[str, Any]) -> Any:
        try:
            response = await self._client.responses.create(**payload)
            if "temperature" in payload:
                self._temperature_supported = True
            return response
        except Exception as exc:
            if "temperature" in str(exc).lower() and "temperature" in payload:
                self._temperature_supported = False
                payload = dict(payload)
                payload.pop("temperature", None)
                return await self._client.responses.create(**payload)
            raise

    def _reasoning_params(self, model_name: str, verbosity: str | None) -> dict[str, Any]:
        model = model_name.lower()
        if model.startswith("gpt-5"):
            selected = verbosity or "low"
            if selected not in {"low", "medium", "high"}:
                selected = "low"
            return {
                "reasoning": {"effort": "minimal"},
                "text": {"verbosity": selected},
            }
        return {}

    @classmethod
    def _extract_text(cls, response: Any) -> str:
        output_text = getattr(response, "output_text", "")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output_items = getattr(response, "output", None)
        if not isinstance(output_items, list):
            return ""

        fragments: list[str] = []
        for item in output_items:
            if cls._read(item, "type") != "message":
                continue
            content = cls._read(item, "content")
            if not isinstance(content, list):
                continue
            for part in content:
                if cls._read(part, "type") not in {"output_text", "text"}:
                    continue
                text = cls._read(part, "text")
                if isinstance(text, str) and text.strip():
                    fragments.append(text.strip())

        return "\n".join(fragments).strip() if fragments else ""

    @staticmethod
    def _read(payload: Any, field: str) -> Any:
        if isinstance(payload, dict):
            return payload.get(field)
        return getattr(payload, field, None)

    @classmethod
    def _is_truncated(cls, response: Any) -> bool:
        status = cls._read(response, "status")
        if status != "incomplete":
            return False
        details = cls._read(response, "incomplete_details")
        reason = cls._read(details, "reason")
        return reason == "max_output_tokens"

    @staticmethod
    def _merge_text_fragments(base_text: str, continuation: str) -> str:
        base = base_text.strip()
        extra = continuation.strip()
        if not extra:
            return base

        if extra in base:
            return base

        # If continuation repeats the ending, keep only the new tail.
        overlap_window = min(140, len(base), len(extra))
        for size in range(overlap_window, 20, -1):
            if base[-size:].strip().lower() == extra[:size].strip().lower():
                extra = extra[size:].lstrip(" \n\t-,:;")
                break

        if not extra:
            return base
        separator = "" if base.endswith(("\n", " ")) else " "
        return f"{base}{separator}{extra}".strip()

    @staticmethod
    def _extract_transcription_text(transcription: Any) -> str:
        if isinstance(transcription, str):
            return transcription.strip()

        text: Any
        if isinstance(transcription, dict):
            text = transcription.get("text")
        else:
            text = getattr(transcription, "text", None)

        if isinstance(text, str):
            return text.strip()
        return ""
