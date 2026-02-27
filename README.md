# Demi Consultant Platform

Production-grade мультиканальная AI платформа косметолога на базе `demi_consultant`.

## Что внутри

- Единое доменное ядро: `ConsultationService`
- Каналы:
  - Telegram (polling)
  - WhatsApp (Meta Cloud API webhook)
  - Instagram (Meta Graph webhook)
- AI возможности:
  - консультации, определение типа кожи, разбор проблемы
  - vision-анализ фото
  - ingredient check (`ChatMode.INGREDIENT_CHECK`)
  - анализ прогресса кожи по фото
- CRM:
  - `InMemoryCRM`
  - `JSONFileCRM`
  - подготовлен интерфейс под PostgreSQL
- Conversion engine: soft offer + эскалация к менеджеру
- Anti-spam + token economy:
  - лимит длины сообщения
  - глобальный rate limit
  - фильтр бессмысленных сообщений
  - detector повторов и abuse
  - token budget guard и тримминг истории
  - short-answer cache

## Структура

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
.gitignore
```

## Быстрый старт

1. Установите зависимости:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Подготовьте `.env`:

```bash
cp .env.example .env
```

3. Заполните обязательные переменные:

- `OPENAI_API_KEY`
- для Telegram: `TELEGRAM_TOKEN`
- для WhatsApp: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN`
- для Instagram: `INSTAGRAM_ACCOUNT_ID`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_VERIFY_TOKEN`

4. Включите нужные каналы:

- `RUN_TELEGRAM=true|false`
- `RUN_WHATSAPP=true|false`
- `RUN_INSTAGRAM=true|false`

5. Запуск:

```bash
python main.py
```

`main.py` поднимает каналы параллельно через `asyncio.gather`.

## Переменные окружения (ключевые)

- Core: `OPENAI_API_KEY`, `MODEL_NAME`, `REQUEST_TIMEOUT_SECONDS`
- Meta: `META_API_VERSION`, `WEBHOOK_HOST`, `WHATSAPP_WEBHOOK_PORT`, `INSTAGRAM_WEBHOOK_PORT`
- CRM: `CRM_ENABLED`, `CRM_STORAGE`, `CRM_JSON_PATH`
- Безопасность: `WHATSAPP_APP_SECRET`, `INSTAGRAM_APP_SECRET`
- Anti-spam: `MAX_USER_TEXT_LENGTH`, `RATE_LIMIT_SECONDS`, `MAX_CONTEXT_TOKENS`, `MAX_IMAGE_SIZE_MB`

Полный список: `.env.example`

## Onboarding flow

При первом контакте:

1. Запрос имени
2. Запрос возрастного диапазона (`<18`, `18-24`, `25-34`, `35-44`, `45+`)
3. Переход в основной режим

Если пользователь игнорирует onboarding, после 2 попыток flow пропускается и диалог продолжается.

## Meta webhook setup

### WhatsApp

1. В Meta App настройте callback URL: `https://<your-domain>/webhook`
2. Verify token должен совпадать с `WHATSAPP_VERIFY_TOKEN`
3. Включите события входящих сообщений
4. Для подписи укажите `WHATSAPP_APP_SECRET`

### Instagram

1. Callback URL: `https://<your-domain>/webhook`
2. Verify token должен совпадать с `INSTAGRAM_VERIFY_TOKEN`
3. Подключите события Instagram Messaging
4. Для подписи используйте `INSTAGRAM_APP_SECRET`

## Деплой на VPS

Минимальный вариант:

1. Запуск через `systemd` или process manager (pm2/supervisor)
2. Reverse proxy (Nginx/Caddy) на webhook-порты
3. HTTPS (обязательно для Meta webhooks)
4. Логи в stdout + сбор через journald/ELK/Loki

## Деплой на Vercel

В проект добавлены:

- `vercel.json` (роутинг в Python serverless entrypoint)
- `api/index.py` (ASGI app для webhook-каналов)

Что важно:

- На Vercel используйте webhook-каналы (`RUN_WHATSAPP=true` и/или `RUN_INSTAGRAM=true`).
- Telegram polling (`RUN_TELEGRAM=true`) для Vercel не подходит.
- `OPENAI_API_KEY` и channel credentials задайте в Vercel Environment Variables.

Webhook URL на Vercel:

- WhatsApp verify/callback: `https://<vercel-domain>/whatsapp/webhook`
- Instagram verify/callback: `https://<vercel-domain>/instagram/webhook`

Проверка:

- `GET https://<vercel-domain>/healthz` -> `{"status":"ok"}`

## Замечания по безопасности

- Не храните реальные ключи в репозитории
- Проверка подписи webhook включена
- Входные payload валидируются
- Ограничен размер изображения
