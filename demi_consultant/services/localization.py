from __future__ import annotations

from typing import Literal

LanguageCode = Literal["ru", "en", "kg"]

DEFAULT_LANGUAGE: LanguageCode = "ru"
SUPPORTED_LANGUAGES: tuple[LanguageCode, ...] = ("ru", "en", "kg")

LANGUAGE_BUTTONS: dict[LanguageCode, str] = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "kg": "🇰🇬 Кыргызча",
}

_LANGUAGE_SELECTION_TEXT = (
    "Здравствуйте 👋\n"
    "Please choose your language 👇\n"
    "Тилди тандаңыз 👇"
)

_TEXTS: dict[str, dict[LanguageCode, str]] = {
    "language_prompt": {
        "ru": _LANGUAGE_SELECTION_TEXT,
        "en": _LANGUAGE_SELECTION_TEXT,
        "kg": _LANGUAGE_SELECTION_TEXT,
    },
    "language_invalid": {
        "ru": "Пожалуйста, выберите язык кнопкой ниже 👇",
        "en": "Please choose the language using the button below 👇",
        "kg": "Сураныч, төмөнкү баскыч аркылуу тил тандаңыз 👇",
    },
    "language_ack_name": {
        "ru": "Отлично 🤍 Буду говорить с вами на русском.\n\nДля начала давайте познакомимся.\nКак к вам можно обращаться?",
        "en": "Great 🤍 I’ll speak with you in English.\n\nFirst, let’s get to know each other.\nWhat’s your name?",
        "kg": "Жакшы 🤍 Мен сиз менен кыргызча сүйлөшөм.\n\nАлгач таанышып алалы.\nСизге кантип кайрылайын?",
    },
    "name_invalid": {
        "ru": "Введите, пожалуйста, только имя (одно слово, без пробелов).",
        "en": "Please enter only your name (one word, no spaces).",
        "kg": "Сураныч, атыңызды гана жазыңыз (бир сөз, боштуксыз).",
    },
    "ask_age": {
        "ru": "Спасибо, {name} 🤍\nЧтобы рекомендации были точнее — подскажите, пожалуйста, ваш возраст.\n\nВведите возраст числом (например: 18)",
        "en": "Thank you, {name} 🤍\nTo make recommendations more accurate, please tell me your age.\n\nEnter your age as a number (for example: 18)",
        "kg": "Рахмат, {name} 🤍\nКеңештер так болушу үчүн, жашыңызды жазыңыз.\n\nЖашыңызды сан менен киргизиңиз (мисалы: 18)",
    },
    "age_invalid": {
        "ru": "Введите корректный возраст числом от 12 до 90.",
        "en": "Please enter a valid age from 12 to 90 as a number.",
        "kg": "12ден 90го чейинки жашты сан менен туура киргизиңиз.",
    },
    "onboarding_done": {
        "ru": "Приятно познакомиться, {name} ✨\nТеперь могу дать более персональные рекомендации.\n\nС чего начнем?",
        "en": "Nice to meet you, {name} ✨\nNow I can give you more personalized recommendations.\n\nWhere would you like to start?",
        "kg": "Таанышканыма кубанычтамын, {name} ✨\nЭми сизге көбүрөөк жеке сунуш бере алам.\n\nЭмнеден баштайбыз?",
    },
    "start_returning_user": {
        "ru": "Рада снова Вас видеть 🤍\nМожем продолжить консультацию: опишите, что сейчас беспокоит по коже.",
        "en": "Glad to see you again 🤍\nWe can continue: please describe what concerns you about your skin right now.",
        "kg": "Кайра көргөнүмө кубанычтамын 🤍\nКеңешти уланталы: азыр териңизде эмне тынчсыздандырып жатканын жазыңыз.",
    },
    "busy_message": {
        "ru": "Секунду, пожалуйста 🤍\nЯ сейчас завершаю ответ на предыдущий вопрос и сразу продолжу диалог.",
        "en": "One second, please 🤍\nI’m finishing the previous reply and will continue right away.",
        "kg": "Бир секунд, сураныч 🤍\nМурунку жоопту бүтүрүп жатам, анан дароо улантам.",
    },
    "thinking_message": {
        "ru": "Думаю над ответом.....",
        "en": "Thinking about your question.....",
        "kg": "Жоопту ойлонуп жатам.....",
    },
    "technical_error": {
        "ru": "Вижу техническую ошибку. Попробуйте через минуту.",
        "en": "I see a technical issue. Please try again in a minute.",
        "kg": "Техникалык ката болуп калды. Бир мүнөттөн кийин кайра аракет кылыңыз.",
    },
    "menu_consultation": {
        "ru": "🔘 Консультация",
        "en": "🔘 Consultation",
        "kg": "🔘 Кеңеш берүү",
    },
    "menu_skin_type": {
        "ru": "🔘 Определить тип кожи",
        "en": "🔘 Identify skin type",
        "kg": "🔘 Тери түрүн аныктоо",
    },
    "menu_problem": {
        "ru": "🔘 Разобрать проблему",
        "en": "🔘 Analyze a concern",
        "kg": "🔘 Маселени талдоо",
    },
    "menu_reply_consultation": {
        "ru": "Отлично, начнем консультацию. Опишите, что хотите улучшить в уходе.",
        "en": "Great, let’s start the consultation. Tell me what you want to improve in your routine.",
        "kg": "Жакшы, консультацияны баштайлы. Кам көрүүдө эмнени жакшырткыңыз келгенин жазыңыз.",
    },
    "menu_reply_skin_type": {
        "ru": "Хорошо, помогу определить тип кожи. Опишите ощущения кожи или отправьте фото без фильтров.",
        "en": "Sure, I can help identify your skin type. Describe your skin sensations or send an unfiltered photo.",
        "kg": "Макул, тери түрүн аныктоого жардам берем. Сезимдериңизди жазыңыз же фильтрсиз сүрөт жөнөтүңүз.",
    },
    "menu_reply_problem": {
        "ru": "Давайте разберем проблему. Опишите, что беспокоит и как давно это проявляется.",
        "en": "Let’s analyze the concern. Please describe what bothers you and for how long.",
        "kg": "Маселени талдайлы. Эмне тынчсыздандырып жатканын жана качантан бери экенин жазыңыз.",
    },
    "low_value": {
        "ru": "Пожалуйста 🤍\nЕсли появятся вопросы по коже — я рядом.",
        "en": "You’re welcome 🤍\nIf you have skincare questions, I’m here.",
        "kg": "Ар дайым жардам берем 🤍\nТери боюнча суроолоруңуз болсо, мен жандамын.",
    },
    "meaningless": {
        "ru": "Похоже, сообщение не распознано 🤍\nПопробуйте написать вопрос словами — я помогу.",
        "en": "It looks like I couldn’t recognize the message.\nPlease type your question, and I’ll help.",
        "kg": "Билдирүү так окулбай калды окшойт.\nСурооңузду текст менен жазыңыз, жардам берем.",
    },
    "text_too_long": {
        "ru": "Сообщение слишком длинное.\nПожалуйста, опишите вопрос кратко (до {limit} символов).",
        "en": "Your message is too long.\nPlease keep it shorter (up to {limit} characters).",
        "kg": "Билдирүү өтө узун болуп калды.\nСураныч, кыскараак жазыңыз ({limit} белгиге чейин).",
    },
    "caption_too_long": {
        "ru": "Подпись к фото слишком длинная.\nПожалуйста, сократите до {limit} символов.",
        "en": "The photo caption is too long.\nPlease shorten it to {limit} characters.",
        "kg": "Сүрөттүн жазуусу өтө узун.\nСураныч, {limit} белгиге чейин кыскартыңыз.",
    },
    "images_limit": {
        "ru": "Давайте остановимся на текущем фото, я уже могу дать рекомендации.",
        "en": "Let’s stop with the current photo; I can already provide recommendations.",
        "kg": "Азыркы сүрөт жетиштүү, эми сунуш бере алам.",
    },
    "image_rate_limit": {
        "ru": "Фото приходят слишком часто.\nОтправляйте не чаще 1 фото в {seconds} секунд.",
        "en": "Photos are coming too frequently.\nPlease send no more than 1 photo every {seconds} seconds.",
        "kg": "Сүрөттөр өтө бат-бат келип жатат.\nАр {seconds} секундда 1 сүрөттөн көп жибербеңиз.",
    },
    "image_size_limit": {
        "ru": "Файл слишком большой.\nМаксимальный размер: {mb} MB.",
        "en": "The file is too large.\nMaximum size: {mb} MB.",
        "kg": "Файл өтө чоң.\nЭң жогорку көлөм: {mb} MB.",
    },
    "domain_redirect": {
        "ru": "Я сфокусирована на коже и уходе 🤍\n\nЕсли хотите, давайте разберем Ваш запрос по типу кожи, проблеме или составу средства.",
        "en": "I’m focused on skincare only 🤍\n\nIf you’d like, we can discuss skin type, concerns, or ingredients.",
        "kg": "Мен тери жана кам көрүү темасына гана жооп берем 🤍\n\nКааласаңыз, тери түрү, маселе же курам боюнча талдап берейин.",
    },
    "domain_redirect_with_fallback": {
        "ru": "{fallback}\n\nЕсли хотите, давайте вернемся к коже: могу помочь с типом кожи, проблемой или составом средства 🤍",
        "en": "{fallback}\n\nIf you want, let’s return to skincare: I can help with skin type, concerns, or ingredient check 🤍",
        "kg": "{fallback}\n\nКааласаңыз, териге кайрылалы: тери түрү, маселе же курам боюнча жардам берем 🤍",
    },
    "close_follow_up": {
        "ru": "Если появятся вопросы по коже — я рядом 🤍",
        "en": "If you have more skincare questions, I’m here 🤍",
        "kg": "Тери боюнча кошумча сурооңуз болсо — мен жандамын 🤍",
    },
    "progress_need_photos": {
        "ru": "Понимаю Ваш вопрос о динамике кожи.\n\nЧтобы оценить изменения точнее, нужен ориентир: фото «до» и текущее фото в похожем свете.\n\nЕсли хотите, отправьте новое фото, и я кратко сравню, что изменилось.",
        "en": "I understand your question about skin progress.\n\nTo assess changes accurately, I need a baseline: a before photo and a current photo in similar lighting.\n\nIf you want, send a new photo and I’ll compare the changes briefly.",
        "kg": "Теринин өзгөрүүсү тууралуу сурооңузду түшүндүм.\n\nТак баалоо үчүн «мурдагы» жана азыркы сүрөт керек (ошол эле жарыкта).\n\nКааласаңыз, жаңы сүрөт жөнөтүңүз, кыскача салыштырып берем.",
    },
    "practical_step": {
        "ru": "Практически: начните с одного действия — добавьте ежедневный SPF, а новые активы вводите постепенно через патч-тест.",
        "en": "Practical step: start with one action — add daily SPF, and introduce new actives gradually with a patch test.",
        "kg": "Практикалык кадам: бир нерседен баштаңыз — күн сайын SPF кошуңуз, жаңы активдерди патч-тест менен акырын киргизиңиз.",
    },
    "uncertainty_question": {
        "ru": "Если хотите, уточните ощущения после умывания или отправьте фото при дневном свете.",
        "en": "If you want, describe how your skin feels after cleansing, or send a daylight photo.",
        "kg": "Кааласаңыз, жуунгандан кийинки сезимдерди жазыңыз же күндүзкү жарыкта сүрөт жөнөтүңүз.",
    },
    "doubt_prefix": {
        "ru": "Вы правы, без фото сложно оценить точно.",
        "en": "You’re right, it’s hard to assess precisely without a photo.",
        "kg": "Туура айтасыз, сүрөтсүз так баалоо кыйын.",
    },
    "tech_pause": {
        "ru": "Вижу небольшую техническую паузу.\nПопробуйте ещё раз через несколько секунд.",
        "en": "I see a brief technical pause.\nPlease try again in a few seconds.",
        "kg": "Кичине техникалык тыныгуу болуп калды.\nБир нече секунддан кийин кайра аракет кылыңыз.",
    },
    "conversion_soft_offer": {
        "ru": "Если хотите, я мягко подберу категории средств под Ваш бюджет и этап ухода.",
        "en": "If you want, I can gently select product categories for your budget and routine stage.",
        "kg": "Кааласаңыз, бюджетиңизге жана кам көрүү этабыңызга ылайык каражат категорияларын тандап берем.",
    },
    "conversion_handoff": {
        "ru": "Если удобно, подключу менеджера: {contact}. При желании передам диалог менеджеру для подбора наличия и финальной комплектации.",
        "en": "If it’s convenient, I can connect our manager: {contact}. If you’d like, I can pass your dialogue for stock check and final set completion.",
        "kg": "Ыңгайлуу болсо, менеджерди кошуп берем: {contact}. Кааласаңыз, диалогду товар бар-жогун тактап, финалдык топтомду чогултуу үчүн өткөрүп берем.",
    },
    "conversion_offer_question": {
        "ru": "Если хотите, могу подобрать уход и средства под Ваш бюджет. Продолжим?",
        "en": "If you want, I can suggest a routine and products for your budget. Shall we continue?",
        "kg": "Кааласаңыз, бюджетиңизге ылайык кам көрүү жана каражаттарды тандап берем. Улантабызбы?",
    },
    "conversion_declined": {
        "ru": "Хорошо, продолжаем консультацию без подбора. Если захотите позже — скажите 🤍",
        "en": "Sure, we can continue without product selection. If you want later, just tell me 🤍",
        "kg": "Макул, тандоо кылбай эле консультацияны улантабыз. Кийин кааласаңыз, айтыңыз 🤍",
    },
    "translator_dry": {
        "ru": "Проще говоря: коже не хватает увлажнения.",
        "en": "Simply put: your skin needs more hydration.",
        "kg": "Жөнөкөй айтканда: териңизге ным жетишпей жатат.",
    },
    "translator_generic": {
        "ru": "Если совсем просто: коже нужен более мягкий и понятный уход.",
        "en": "In simple words: your skin needs a gentler and clearer routine.",
        "kg": "Жөнөкөй айтканда: териңизге жумшак жана түшүнүктүү кам көрүү керек.",
    },
    "warmth_prefix": {
        "ru": "Если говорить проще,",
        "en": "To put it simply,",
        "kg": "Жөнөкөй айтсам,",
    },
    "topic_why": {
        "ru": "Почему так бывает",
        "en": "Why this happens",
        "kg": "Эмне үчүн ушундай болот",
    },
    "topic_now": {
        "ru": "Что делать сейчас",
        "en": "What to do now",
        "kg": "Азыр эмне кылуу керек",
    },
    "topic_important": {
        "ru": "Важно",
        "en": "Important",
        "kg": "Маанилүү",
    },
}

_FALLBACK_BY_MODE: dict[LanguageCode, dict[str, str]] = {
    "ru": {
        "consultation": "Понимаю Ваш запрос. Давайте мягко разберем уход по шагам и добавим безопасный следующий шаг.",
        "skin_type": "Понимаю Ваш запрос. Дам ориентир по типу кожи и практическую рекомендацию по уходу.",
        "problem": "Понимаю, это может беспокоить. Давайте разберем ситуацию и выберем безопасный план действий.",
        "ingredient": "Очень хороший вопрос. Давайте разберем состав по безопасности и практическому применению.",
        "chat": "Понимаю Ваш вопрос. Давайте разберем его и определим конкретный следующий шаг по уходу.",
    },
    "en": {
        "consultation": "I understand your request. Let’s go step by step and choose a safe next skincare action.",
        "skin_type": "I understand your request. I’ll give a skin type direction and one practical care step.",
        "problem": "I understand your concern. Let’s review it and choose a safe action plan.",
        "ingredient": "Great question. Let’s review the formula for safety and practical use.",
        "chat": "I understand your question. Let’s break it down and define the next practical step.",
    },
    "kg": {
        "consultation": "Сурооңузду түшүндүм. Кам көрүүнү кадам-кадам менен талдап, коопсуз кийинки кадамды тандайлы.",
        "skin_type": "Сурооңузду түшүндүм. Тери түрү боюнча багыт берип, практикалык сунуш айтам.",
        "problem": "Тынчсызданууңузду түшүндүм. Маселени талдап, коопсуз план тандайлы.",
        "ingredient": "Жакшы суроо. Курамды коопсуздук жана колдонуу боюнча талдайлы.",
        "chat": "Сурооңузду түшүндүм. Кыскача талдап, кийинки практикалык кадамды аныктайлы.",
    },
}

_SOFT_CLOSINGS: dict[LanguageCode, tuple[str, ...]] = {
    "ru": (
        "Если хотите, можем разобрать это глубже или перейти к другой теме ухода.",
        "Если нужно, могу подобрать уход под Вашу кожу без лишних средств.",
        "Могу также разобрать Ваш текущий уход или помочь определить тип кожи.",
        "Если появятся вопросы по коже — я рядом 🤍",
    ),
    "en": (
        "If you want, we can go deeper or switch to another skincare topic.",
        "If needed, I can suggest a routine without unnecessary products.",
        "I can also review your current routine or help identify skin type.",
        "If you have more skincare questions — I’m here 🤍",
    ),
    "kg": (
        "Кааласаңыз, муну тереңирээк талдап же башка кам көрүү темасына өтөлү.",
        "Керек болсо, ашыкча каражатсыз кам көрүү тандап берем.",
        "Кааласаңыз, учурдагы кам көрүүңүздү талдап же тери түрүн аныктоого жардам берем.",
        "Тери боюнча суроолоруңуз болсо — мен жандамын 🤍",
    ),
}

_CTA_STARTERS: dict[LanguageCode, tuple[str, ...]] = {
    "ru": ("если хотите", "если нужно", "если удобно", "могу", "подключу менеджера", "передам диалог", "при желании"),
    "en": ("if you want", "if needed", "if you'd like", "i can", "i may", "i can also"),
    "kg": ("кааласаңыз", "керек болсо", "ылайыктуу болсо", "мен", "жардам бере алам"),
}


def normalize_language(language: str | None) -> LanguageCode:
    value = str(language or "").strip().lower()
    if value in SUPPORTED_LANGUAGES:
        return value  # type: ignore[return-value]
    return DEFAULT_LANGUAGE


def resolve_language_choice(text: str) -> LanguageCode | None:
    normalized = " ".join(str(text or "").lower().split())
    mapping = {
        "🇷🇺 русский": "ru",
        "русский": "ru",
        "ru": "ru",
        "russian": "ru",
        "🇬🇧 english": "en",
        "english": "en",
        "en": "en",
        "🇰🇬 кыргызча": "kg",
        "кыргызча": "kg",
        "кыргыз": "kg",
        "kg": "kg",
        "ky": "kg",
    }
    code = mapping.get(normalized)
    if code is None:
        return None
    return code  # type: ignore[return-value]


def text(key: str, language: str | None = None, **kwargs: object) -> str:
    lang = normalize_language(language)
    variants = _TEXTS.get(key)
    if not variants:
        return ""
    template = variants.get(lang) or variants.get(DEFAULT_LANGUAGE) or ""
    if kwargs:
        return template.format(**kwargs)
    return template


def menu_buttons(language: str | None = None) -> tuple[str, str, str]:
    lang = normalize_language(language)
    return (
        text("menu_consultation", lang),
        text("menu_skin_type", lang),
        text("menu_problem", lang),
    )


def menu_labels_normalized(language: str | None = None) -> set[str]:
    items = menu_buttons(language)
    labels: set[str] = set()
    for item in items:
        normalized = " ".join(item.lower().split())
        labels.add(normalized)
        labels.add(normalized.replace("🔘", "").strip())
    return labels


def fallback_by_mode(language: str | None, mode_key: str) -> str:
    lang = normalize_language(language)
    table = _FALLBACK_BY_MODE.get(lang) or _FALLBACK_BY_MODE[DEFAULT_LANGUAGE]
    return table.get(mode_key, table["chat"])


def soft_closings(language: str | None = None) -> tuple[str, ...]:
    lang = normalize_language(language)
    return _SOFT_CLOSINGS.get(lang, _SOFT_CLOSINGS[DEFAULT_LANGUAGE])


def all_soft_closings() -> tuple[str, ...]:
    seen: list[str] = []
    for items in _SOFT_CLOSINGS.values():
        for item in items:
            if item not in seen:
                seen.append(item)
    return tuple(seen)


def cta_starters(language: str | None = None) -> tuple[str, ...]:
    lang = normalize_language(language)
    return _CTA_STARTERS.get(lang, _CTA_STARTERS[DEFAULT_LANGUAGE])


def language_instruction(language: str | None = None) -> str:
    lang = normalize_language(language)
    if lang == "en":
        return "Reply strictly in English. Do not use Russian or Kyrgyz in the final answer."
    if lang == "kg":
        return "Жоопту катуу кыргыз тилинде жазыңыз. Финалдык жоопко орусча же англисче аралаштырбаңыз."
    return "Отвечайте строго на русском языке."


def language_name(language: str | None = None) -> str:
    lang = normalize_language(language)
    return {
        "ru": "Русский",
        "en": "English",
        "kg": "Кыргызча",
    }[lang]
