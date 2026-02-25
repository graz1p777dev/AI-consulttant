from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from demi_consultant.services.onboarding_service import OnboardingService


class StartHandler:
    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        await update.message.reply_text(
            OnboardingService.START_MESSAGE,
            reply_to_message_id=update.message.message_id,
        )
