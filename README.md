# Demi Consultant Platform

Production-grade мультиканальная AI платформа косметолога на базе `demi_consultant`.

## Что внутри

- Единое доменное ядро: `ConsultationService`
- Каналы:
  - Telegram (polling)
  - WhatsApp (Meta Cloud API webhook)
  - Instagram (Meta Graph webhook)
  - HTTP API (FastAPI) для терминала/сайта
- AI возможности:
  - консультации, определение типа кожи, разбор проблемы
  - распознавание voice/audio (Telegram, WhatsApp, Instagram) -> текст -> ответ AI
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
- `RUN_API=true|false`

5. Запуск:

```bash
python main.py
```

`main.py` поднимает каналы параллельно через `asyncio.gather`.

## Переменные окружения (ключевые)

- Core: `OPENAI_API_KEY`, `MODEL_NAME`, `REQUEST_TIMEOUT_SECONDS`
- Audio: `VOICE_REPLY_MODEL` (default `gpt-4o-mini`), `AUDIO_TRANSCRIBE_MODEL` (default `gpt-4o-mini-transcribe`)
- Telegram: `TELEGRAM_PROXY_URL` (optional, if direct access to `api.telegram.org` is blocked)
- API: `RUN_API`, `API_HOST`, `API_PORT`, `API_BEARER_TOKEN` (optional bearer auth)
- Meta: `META_API_VERSION`, `WEBHOOK_HOST`, `WHATSAPP_WEBHOOK_PORT`, `INSTAGRAM_WEBHOOK_PORT`
- CRM: `CRM_ENABLED`, `CRM_STORAGE`, `CRM_JSON_PATH`
- Безопасность: `WHATSAPP_APP_SECRET`, `INSTAGRAM_APP_SECRET`
- Anti-spam: `MAX_USER_TEXT_LENGTH`, `RATE_LIMIT_SECONDS`, `MAX_CONTEXT_TOKENS`, `MAX_IMAGE_SIZE_MB`

Полный список: `.env.example`

## HTTP API (терминал/сайт)

Если `RUN_API=true`, `main.py` поднимет API на `API_HOST:API_PORT` (по умолчанию `0.0.0.0:8090`).

Проверка:

```bash
curl http://127.0.0.1:8090/healthz
```

Текстовый запрос:

```bash
curl -X POST http://127.0.0.1:8090/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"web-user-1","text":"У меня сухая кожа после умывания"}'
```

Если включен `API_BEARER_TOKEN`, добавляйте заголовок:

```bash
-H "Authorization: Bearer <token>"
```

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

### Вариант 1: Docker (рекомендуется)

1. Подготовьте `.env`:

```bash
cp .env.example .env
```

2. Заполните переменные в `.env` (минимум `OPENAI_API_KEY` и токены выбранных каналов).

3. Запуск в Docker Compose:

```bash
docker compose up -d --build
```

4. Проверка:

```bash
docker compose ps
docker compose logs -f demi-consultant
```

Что важно:

- Контейнер публикует webhook-порты `8081` (WhatsApp) и `8082` (Instagram).
- Данные CRM (json) сохраняются в `./data` на хосте.
- Для внешнего доступа поставьте reverse proxy (Nginx/Caddy) и HTTPS.

### Вариант 2: Без Docker

1. Запуск через `systemd` или process manager (pm2/supervisor)
2. Reverse proxy (Nginx/Caddy) на webhook-порты
3. HTTPS (обязательно для Meta webhooks)
4. Логи в stdout + сбор через journald/ELK/Loki

## Деплой на Vercel (Telegram only)

В проект добавлены:

- `vercel.json` (роутинг в Python serverless entrypoint)
- `api/index.py` + `api/app.py` (ASGI app для Telegram webhook)

Что важно:

- Для Vercel используйте Telegram webhook (не polling).
- `RUN_TELEGRAM=true`, `RUN_WHATSAPP=false`, `RUN_INSTAGRAM=false`.
- Задайте в Vercel env: `OPENAI_API_KEY`, `TELEGRAM_TOKEN`.
- Опционально: `TELEGRAM_WEBHOOK_SECRET` для защиты webhook.

Webhook URL на Vercel:

- Telegram webhook: `https://<vercel-domain>/telegram/webhook`

Проверка:

- `GET https://<vercel-domain>/healthz` -> `{"status":"ok"}`

## Замечания по безопасности

- Не храните реальные ключи в репозитории
- Проверка подписи webhook включена
- Входные payload валидируются
- Ограничен размер изображения
