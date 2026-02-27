from __future__ import annotations

from demi_consultant.services.intent_router import IntentResult
from demi_consultant.services.localization import normalize_language, text
from demi_consultant.services.reasoning_planner import Plan


class ReactionSelector:
    """Deterministic reaction selector. No random starters."""

    def select_reaction(
        self,
        *,
        intent: IntentResult,
        plan: Plan,
        has_photo: bool,
        user_text: str,
        language: str | None = None,
        previous_opening: str = "",
    ) -> str:
        lang = normalize_language(language)
        lowered = user_text.lower()

        if any(
            marker in lowered
            for marker in (
                "сомнева",
                "не уверен",
                "не уверена",
                "вдруг",
                "не похоже",
                "not sure",
                "i doubt",
                "i'm not sure",
                "так эмес",
                "ишенбейм",
            )
        ):
            return text("doubt_prefix", lang)

        if has_photo:
            if lang == "en":
                return "Thanks for the photo, this helps me assess the situation more accurately."
            if lang == "kg":
                return "Сүрөт үчүн рахмат, бул абалды такыраак баалоого жардам берет."
            return "Спасибо за фото, это помогает точнее оценить ситуацию."

        if intent.intent_type == "question":
            reaction = {
                "ru": "Очень хороший вопрос.",
                "en": "Great question.",
                "kg": "Абдан жакшы суроо.",
            }[lang]
        elif intent.intent_type == "complaint":
            reaction = {
                "ru": "Понимаю, такое бывает довольно часто.",
                "en": "I understand, this is quite common.",
                "kg": "Түшүндүм, мындай абал көп кездешет.",
            }[lang]
        elif intent.intent_type == "emotion":
            reaction = {
                "ru": "Понимаю Ваши переживания.",
                "en": "I understand your concerns.",
                "kg": "Тынчсызданууңузду түшүнөм.",
            }[lang]
        elif intent.intent_type == "follow_up":
            reaction = ""
        elif intent.intent_type == "purchase":
            reaction = {
                "ru": "Понимаю Ваш запрос.",
                "en": "I understand your request.",
                "kg": "Сурамыңызды түшүндүм.",
            }[lang]
        else:
            reaction = {
                "ru": "Понимаю Ваш запрос.",
                "en": "I understand your request.",
                "kg": "Сурамыңызды түшүндүм.",
            }[lang]

        if previous_opening and reaction and previous_opening.strip().lower() == reaction.strip().lower():
            if plan.reaction_type == "question_reaction":
                return {
                    "ru": "Разберем по шагам, чтобы было понятно и без лишнего.",
                    "en": "Let’s break it down step by step, clearly and without extra details.",
                    "kg": "Кадам-кадам талдап берейин, так жана ашыкча сөзсүз.",
                }[lang]
            if plan.reaction_type in {"empathy", "validation"}:
                return {
                    "ru": "С Вами, давайте спокойно подберем рабочий и мягкий вариант.",
                    "en": "I’m with you, let’s calmly choose a gentle and effective option.",
                    "kg": "Сиз мененмин, жай жана жумшак, иштей турган вариант тандайлы.",
                }[lang]
            return {
                "ru": "Продолжим по делу и подстроим уход под Ваш запрос.",
                "en": "Let’s continue and tailor the routine to your request.",
                "kg": "Уланталы, кам көрүүнү сурамыңызга ылайыктап берейин.",
            }[lang]

        return reaction
