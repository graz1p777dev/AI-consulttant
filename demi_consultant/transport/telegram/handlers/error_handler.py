from __future__ import annotations

import logging

from telegram import Update
from telegram.error import Conflict
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        logger.error("Polling conflict: another Telegram polling instance is running")
        context.application.stop_running()
        return

    logger.exception("Unhandled Telegram error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text("Вижу техническую ошибку. Попробуйте через минуту.")
