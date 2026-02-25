# AGENTS.md

Инструкции для ИИ-агента, который впервые открывает проект `Demi-Konsultant`.

## 1) Цель проекта

`Demi-Konsultant` это production-ready AI платформа косметолога Demi Results.

Главное:
- только косметология и уход за кожей;
- никаких legacy-сценариев про ПК/компьютеры;
- единое доменное ядро: `ConsultationService`;
- транспортные слои (Telegram/WhatsApp/Instagram) должны быть тонкими адаптерами.

## 2) Архитектура

Корень:

```text
/demi_consultant
  /ai
  /core
  /services
  /state
  /transport
    /telegram
    /whatsapp
    /instagram
  /integrations
    /crm
    /meta_api
  /knowledge
  bootstrap.py

main.py
requirements.txt
.env.example
README.md
```

Ключевые точки:
- `main.py` — запуск каналов параллельно (`asyncio.gather`).
- `demi_consultant/bootstrap.py` — сборка `ConsultationService`.
- `demi_consultant/services/consultation_service.py` — доменное ядро.
- `demi_consultant/transport/*` — обработка транспорта без бизнес-дублирования.

## 3) Жесткие продуктовые правила

- Бот должен быть только AI косметологом Demi Results.
- Нельзя возвращать legacy-логику ПК-консультанта.
- Общение уважительное, на "Вы", без диагнозов и без фамильярности.
- После onboarding Telegram должен работать в свободном чате, без возврата к кнопкам.
- Любой канал должен использовать общий доменный сервис, а не отдельную логику.

## 4) Telegram UX (обязательно)

- `/start` отправляет фиксированное приветствие косметолога.
- Onboarding:
  - шаг 1: имя (одно слово, только буквы, длина 2-20);
  - шаг 2: возраст (число 12-90).
- После валидного возраста:
  - одноразово показать reply keyboard:
    - `🔘 Консультация`
    - `🔘 Определить тип кожи`
    - `🔘 Разобрать проблему`
  - после выбора убрать клавиатуру (`ReplyKeyboardRemove`).
- Дальше только свободный conversational режим.

## 5) Anti-spam и token economy

- `MAX_USER_TEXT_LENGTH=150` для текста/caption.
- Первые 5 сообщений пользователя без cooldown.
- Начиная с 6-го: rate limit 1 ответ / 6 секунд.
- Repeated detector:
  - 3 одинаковых подряд -> игнор 3-го;
  - 5 одинаковых -> mute 30 секунд.
- Abuse guard:
  - 10+ сообщений за минуту -> block 60 секунд.

## 6) AI и ответы

- Используется OpenAI Responses API (`gpt-5-mini` по умолчанию).
- Ответ должен содержать:
  1. реакцию,
  2. мягкую оценку,
  3. основной ответ,
  4. практический шаг,
  5. мягкое продолжение диалога.
- Ingredient-check режим обязателен (`ChatMode.INGREDIENT_CHECK`).
- Vision поддерживается для фото, включая progress-анализ.

## 7) CRM и knowledge

- CRM слой: `InMemoryCRM`, `JSONFileCRM` (+ интерфейс под postgres).
- События: consultation_started, skin_type_detected, problem_detected, recommendation_given, purchase_intent.
- Knowledge-файлы:
  - `knowledge/store_profile.json`
  - `knowledge/allowed_ingredients.json`
  - `knowledge/conversion_rules.json`

## 8) Перед изменениями и после изменений

Перед изменениями:
- сначала найди, где проходит текущий поток пользователя через `ConsultationService`;
- не дублируй доменную логику в transport-слое.

После изменений:
- прогоняй:
  - `./venv/bin/python -m ruff check demi_consultant main.py`
  - `./venv/bin/python -m compileall demi_consultant main.py`
- проверь, что не появились тексты/ветки legacy ПК-консультанта.

## 9) Быстрый запуск для локальной проверки

1. Заполни `.env` (минимум `OPENAI_API_KEY` и `TELEGRAM_TOKEN`).
2. Для проверки только Telegram:
   - `RUN_TELEGRAM=true`
   - `RUN_WHATSAPP=false`
   - `RUN_INSTAGRAM=false`
3. Запуск:
   - `./venv/bin/python main.py`

## 10) Definition of done для задач

Задача считается завершенной, если:
- реализована через текущее доменное ядро;
- не нарушает UX onboarding и свободного диалога;
- не ломает anti-spam и guardrails;
- проходит lint + compile;
- не возвращает legacy ПК-контент ни в одном канале.
