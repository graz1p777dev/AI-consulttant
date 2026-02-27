from __future__ import annotations

import re
from typing import Any

from demi_consultant.knowledge.knowledge_loader import KnowledgeBundle
from demi_consultant.services.localization import language_instruction, language_name, normalize_language
from demi_consultant.state.fsm import ChatMode
from demi_consultant.state.user_session import UserSession

BASE_IDENTITY_PROMPT = """
Вы — AI косметолог-консультант Demi Results.
Только skincare: кожа, уход, ингредиенты и составы.
Без диагнозов, без оффтопа, без legacy-тем про ПК.
Тон: уважительно на «Вы», спокойно, профессионально, без давления.
""".strip()

SAFETY_RULES = """
Без фото не делайте визуальных выводов.
Не додумывайте симптомы, которых не было в тексте.
При нехватке данных пишите мягко: «возможно», «чаще всего».
Если пользователь сомневается — не спорьте, признайте ограничения и уточните данные.
Лучше честность, чем уверенность без данных.
Никогда не называйте бренды и марки косметики, только категории и состав/активы.
""".strip()

STYLE_RULES = """
Формат как в мессенджере: короткие абзацы и живой ритм.
Сначала реакция по смыслу, затем суть и практический шаг.
Без канцелярита, лекций и шаблонных заголовков.
Списки и таблицы только если пользователь попросил.

Длина ответа:
— Отвечайте кратко и по делу.
— Цель: формат живого мессенджера, не статьи.
— 4–8 строк в большинстве случаев.
— Максимум 120–150 слов.
— Не давать длинные лекции без запроса пользователя.
— Если тема сложная: дайте короткую суть, предложите углубиться по желанию.
— Принцип: сначала кратко → глубже только если попросят.

Стратегия ответа:
— Сначала короткий полезный ответ.
— Затем (опционально) 1 мягкое предложение продолжить.
— Не перечисляйте длинные списки без запроса.
— Не делайте много подпунктов.

Если можно ответить проще — отвечайте проще.

Запрещено:
— академический стиль
— длинные методички
— многоуровневые списки
— ощущение статьи
""".strip()

EMOTIONALITY_RULES = """
Добавляйте лёгкую эмоциональность в ответы:
— тёплый тон
— спокойная поддержка
— человеческие формулировки

Иногда можно:
— короткое эмодзи (не всегда)
— мягкие слова поддержки
— живые переходы

Но:
— без инфантилизма
— без перегиба
— без «солнышко зайчик»
— не в каждом ответе
""".strip()

TECHNICAL_QUALITY_RULES = """
Technical quality: финальный текст должен быть цельным, без обрывов и broken chunks.
""".strip()

SHORT_STYLE_RULES = """
Короткий ответ в чат-формате: по делу, без лекции.
Одна мысль на абзац.
""".strip()

CONFIDENCE_LOW_BLOCK = """
Confidence mode:
— используйте мягкие формулировки
— слова: возможно, ориентировочно, чаще всего
— избегайте категоричных выводов
""".strip()


def _compose_base_prompt(style_block: str) -> str:
    return "\n\n".join([BASE_IDENTITY_PROMPT, SAFETY_RULES, style_block, EMOTIONALITY_RULES]).strip()


BASE_PROMPT = _compose_base_prompt(STYLE_RULES)

CONSULTATION_APPENDIX = """
Режим: консультация.

Дайте:
- мягкий и понятный разбор запроса,
- безопасную схему ухода,
- конкретный следующий шаг.
""".strip()

SKIN_TYPE_APPENDIX = """
Режим: определить тип кожи.

Дайте:
- ориентир типа кожи по описанию клиента (без категоричности),
- краткое обоснование,
- как минимум 1 практическую рекомендацию.
""".strip()

PROBLEM_SOLVING_APPENDIX = """
Режим: разобрать проблему.

Дайте:
- мягкую оценку ситуации,
- объяснение вероятных причин (без диагноза),
- рабочий план с безопасным вводом активов.
""".strip()

INGREDIENT_APPENDIX = """
Режим: ingredient check.

Структура оценки состава:
✔ безопасно
⚠ осторожно
❌ нежелательно

Оценивайте:
- комедогенность,
- раздражающие компоненты,
- маркетинговый шум без пользы.
""".strip()

SOFT_CLOSING_BLOCK = """
Завершение ответа (используйте один вариант):
- "Если хотите, можем разобрать это глубже или перейти к другой теме ухода."
- "Если нужно, могу подобрать уход под Вашу кожу без лишних средств."
- "Могу также разобрать Ваш текущий уход или помочь определить тип кожи."
- "Если появятся вопросы по коже — я рядом 🤍"
""".strip()


def build_system_prompt(
    mode: ChatMode,
    session: UserSession,
    knowledge: KnowledgeBundle,
    runtime_guidance: str | dict[str, Any] | None = None,
) -> str:
    runtime_text, runtime_flags = _parse_runtime_guidance(runtime_guidance)
    style_block = _select_style_block(mode, session)
    base_prompt = _compose_base_prompt(style_block)

    mode_block = {
        ChatMode.CONSULTATION: CONSULTATION_APPENDIX,
        ChatMode.SKIN_TYPE: SKIN_TYPE_APPENDIX,
        ChatMode.PROBLEM_SOLVING: PROBLEM_SOLVING_APPENDIX,
        ChatMode.INGREDIENT_CHECK: INGREDIENT_APPENDIX,
        ChatMode.CHAT: CONSULTATION_APPENDIX,
    }[mode]

    store_profile = knowledge.store_profile
    ingredients = knowledge.allowed_ingredients

    concerns_items = [session.concerns] if session.concerns else None
    allergy_items = [session.allergies] if session.allergies else None
    recommendation_items = session.last_recommendations if session.last_recommendations else None

    profile_block = "\n".join(
        [
            f"Язык: {language_name(session.language)} ({normalize_language(session.language)})",
            f"Имя: {_safe_text(session.name, fallback='не указано', max_len=24)}",
            f"Возраст: {session.age if session.age is not None else 'не указан'}",
            f"Тип кожи: {_safe_text(session.skin_type, fallback='не указан', max_len=20)}",
            f"Сообщений в консультации: {session.consultation_turns}",
            f"Жалобы: {_safe_join(concerns_items, limit=1)}",
            f"Аллергии: {_safe_join(allergy_items, limit=1)}",
            f"Последние рекомендации: {_safe_join(recommendation_items, limit=2)}",
        ]
    )

    store_block = (
        "Store context: "
        f"philosophy={store_profile.get('philosophy', 'ingredient-first')}; "
        f"tone={store_profile.get('brand_tone', 'premium clinic')}."
    )

    ingredients_block = "\n".join(
        [
            "Ingredient-first logic:",
            f"- whitelist: {', '.join(map(str, ingredients.get('whitelist', [])))}",
            f"- blacklist: {', '.join(map(str, ingredients.get('blacklist', [])))}",
        ]
    )

    age_block = _age_adaptation_block(session.age_range)

    conversion_block = (
        "Conversion awareness: первые 5 сообщений в консультации отвечайте без продажных CTA. "
        "Начиная с 6-го можно мягко предложить подбор под бюджет одной фразой. "
        "Если пользователь согласился, дайте контакт консультанта и шаг обращения. Без давления."
    )

    language_block = language_instruction(session.language)
    parts = [base_prompt, language_block, mode_block, conversion_block, profile_block]
    if mode == ChatMode.INGREDIENT_CHECK:
        parts.append(ingredients_block)
    if session.purchase_stage == "hot_lead":
        parts.append(store_block)
    if session.age is not None:
        parts.append(age_block)
    if runtime_text:
        parts.append(runtime_text)
    if mode != ChatMode.INGREDIENT_CHECK and runtime_flags.get("enable_soft_closing", False):
        parts.append(SOFT_CLOSING_BLOCK)
    if runtime_flags.get("confidence") == "low":
        parts.append(CONFIDENCE_LOW_BLOCK)
    parts.append(TECHNICAL_QUALITY_RULES)

    return "\n\n".join(part for part in parts if part.strip())


def _age_adaptation_block(age_range: str | None) -> str:
    _ = age_range
    return (
        "Age adaptation: учитывайте переносимость активов и реактивность кожи в динамике; "
        "не делайте выводы о типе кожи по возрасту и не используйте фразу «в вашем возрасте кожа»."
    )


def _select_style_block(mode: ChatMode, session: UserSession) -> str:
    no_photo_context = not bool(session.progress_photos)
    no_problem_context = not bool((session.concerns or "").strip())
    if mode == ChatMode.CHAT and no_photo_context and no_problem_context:
        return SHORT_STYLE_RULES
    return STYLE_RULES


def _safe_join(items: list[str] | None, limit: int = 3, max_len: int = 40) -> str:
    if not items:
        return "нет"
    cleaned: list[str] = []
    for item in items[-limit:]:
        normalized = re.sub(r"\s+", " ", str(item)).strip()
        if not normalized:
            continue
        cleaned.append(normalized[:max_len])
    return ", ".join(cleaned) if cleaned else "нет"


def _safe_text(value: str | None, *, fallback: str, max_len: int = 40) -> str:
    if not value:
        return fallback
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    if not normalized:
        return fallback
    return normalized[:max_len]


def _safe_multiline_text(value: str | None, max_len: int = 900) -> str:
    if not value:
        return ""
    normalized = str(value).replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()[:max_len]


def _parse_runtime_guidance(runtime_guidance: str | dict[str, Any] | None) -> tuple[str, dict[str, str | bool]]:
    flags: dict[str, str | bool] = {
        "enable_soft_closing": False,
        "confidence": "",
    }
    if runtime_guidance is None:
        return "", flags

    if isinstance(runtime_guidance, dict):
        raw_text = runtime_guidance.get("text", "")
        text = _safe_multiline_text(str(raw_text), max_len=900)
        flags["enable_soft_closing"] = bool(runtime_guidance.get("enable_soft_closing", False))
        confidence = runtime_guidance.get("confidence")
        flags["confidence"] = str(confidence).strip().lower() if confidence is not None else ""
        return text, flags

    text = str(runtime_guidance).strip()
    soft_closing_matches = re.findall(
        r"(?im)^\s*enable_soft_closing\s*=\s*(true|false)\s*$",
        text,
    )
    if soft_closing_matches:
        flags["enable_soft_closing"] = soft_closing_matches[-1].lower() == "true"
        text = re.sub(r"(?im)^\s*enable_soft_closing\s*=\s*(true|false)\s*$", "", text)

    confidence_matches = re.findall(
        r"(?im)^\s*confidence\s*=\s*(low|high)\s*$",
        text,
    )
    if confidence_matches:
        flags["confidence"] = confidence_matches[-1].lower()
        text = re.sub(r"(?im)^\s*confidence\s*=\s*(low|high)\s*$", "", text)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = _safe_multiline_text(text, max_len=900)
    return text, flags
