from __future__ import annotations

from demi_consultant.ai.openai_client import OpenAIClient


class SkinProgressService:
    def __init__(self, openai_client: OpenAIClient) -> None:
        self._openai_client = openai_client

    async def compare_photos(
        self,
        old_photo: bytes,
        new_photo: bytes,
        *,
        old_mime_type: str = "image/jpeg",
        new_mime_type: str = "image/jpeg",
    ) -> str:
        prompt = (
            "Сравни состояние кожи и оцени прогресс. "
            "Опиши динамику нейтрально, без диагноза. "
            "Структура: 1) что улучшилось 2) что требует внимания 3) практический следующий шаг."
        )
        return await self._openai_client.generate_reply_with_images(
            system_prompt=(
                "Ты AI косметолог-консультант. Анализируй только визуальные признаки, "
                "не ставь диагноз и сохраняй бережный тон."
            ),
            dialogue=[],
            images=[
                (old_photo, old_mime_type),
                (new_photo, new_mime_type),
            ],
            user_text=prompt,
            # TEMP: повышаем лимит, чтобы не получать обрезанные ответы в прогрессе.
            max_output_tokens=900,
            verbosity="low",
        )
