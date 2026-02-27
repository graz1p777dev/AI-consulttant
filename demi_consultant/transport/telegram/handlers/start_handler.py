from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from demi_consultant.services.onboarding_service import OnboardingService
from demi_consultant.transport.telegram.keyboards.main import build_language_keyboard


class StartHandler:
    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        await update.message.reply_text(
            OnboardingService.START_MESSAGE,
            reply_markup=build_language_keyboard(),
            reply_to_message_id=update.message.message_id,
        )
