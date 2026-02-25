from __future__ import annotations

from telegram import ReplyKeyboardMarkup

BUTTON_AI_CONSULTATION = "🔘 Консультация"
BUTTON_SKIN_TYPE = "🔘 Определить тип кожи"
BUTTON_PROBLEM_SOLVING = "🔘 Разобрать проблему"


def build_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [BUTTON_AI_CONSULTATION],
            [BUTTON_SKIN_TYPE],
            [BUTTON_PROBLEM_SOLVING],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
