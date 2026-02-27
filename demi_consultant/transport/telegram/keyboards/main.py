from __future__ import annotations

from telegram import ReplyKeyboardMarkup

from demi_consultant.services.localization import LANGUAGE_BUTTONS, menu_buttons

BUTTON_AI_CONSULTATION = menu_buttons("ru")[0]
BUTTON_SKIN_TYPE = menu_buttons("ru")[1]
BUTTON_PROBLEM_SOLVING = menu_buttons("ru")[2]


def build_language_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [LANGUAGE_BUTTONS["ru"]],
            [LANGUAGE_BUTTONS["en"]],
            [LANGUAGE_BUTTONS["kg"]],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_main_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    consultation, skin_type, problem = menu_buttons(language)
    return ReplyKeyboardMarkup(
        keyboard=[
            [consultation],
            [skin_type],
            [problem],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
