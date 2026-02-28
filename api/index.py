from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from telegram import Update

from demi_consultant.bootstrap import build_consultation_service
from demi_consultant.core.config import get_settings
from demi_consultant.core.logger import configure_logging
from demi_consultant.transport.rate_limit import RateLimiter
from demi_consultant.transport.telegram.telegram_bot import TelegramCosmoBot

logger = logging.getLogger(__name__)

app = FastAPI(title="Demi Consultant Telegram API")
_init_lock = asyncio.Lock()
_initialized = False
_telegram_app = None
_telegram_secret = None


def _is_enabled(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def _ensure_initialized() -> None:
    global _initialized, _telegram_app, _telegram_secret
    if _initialized:
        return

    async with _init_lock:
        if _initialized:
            return

        settings = get_settings()
        configure_logging(settings.debug)

        if not settings.telegram_configured:
            raise RuntimeError("TELEGRAM_TOKEN is missing")

        limiter = RateLimiter(interval_seconds=settings.rate_limit_seconds)
        consultation_service = build_consultation_service(settings, rate_limiter=limiter)
        telegram_bot = TelegramCosmoBot(settings=settings, consultation_service=consultation_service)

        telegram_bot._register_handlers()  # noqa: SLF001
        _telegram_app = telegram_bot._application  # noqa: SLF001
        await _telegram_app.initialize()
        await _telegram_app.start()

        _telegram_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip() or None

        # Keep manual webhook control by default.
        auto_set_webhook = _is_enabled(os.getenv("AUTO_SET_TELEGRAM_WEBHOOK"))
        vercel_url = os.getenv("VERCEL_PROJECT_PRODUCTION_URL") or os.getenv("VERCEL_URL")
        if auto_set_webhook and vercel_url:
            webhook_url = f"https://{vercel_url}/webhook"
            await _telegram_app.bot.set_webhook(
                url=webhook_url,
                secret_token=_telegram_secret,
                drop_pending_updates=False,
                allowed_updates=["message"],
            )

        _initialized = True


@app.on_event("startup")
async def _startup() -> None:
    await _ensure_initialized()


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _telegram_app is None:
        return
    await _telegram_app.stop()
    await _telegram_app.shutdown()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/healthz")
async def healthz_webhook(request: Request) -> dict[str, bool]:
    # Fallback webhook endpoint: useful when edge routing rewrites custom paths.
    return await _handle_telegram_webhook(request)


@app.get("/telegram/webhook")
async def telegram_webhook_get() -> dict[str, str]:
    await _ensure_initialized()
    return {"status": "ok"}


@app.get("/webhook")
async def webhook_get() -> dict[str, str]:
    await _ensure_initialized()
    return {"status": "ok"}


@app.get("/")
async def root_get() -> dict[str, str]:
    await _ensure_initialized()
    return {"status": "ok"}


async def _handle_telegram_webhook(request: Request) -> dict[str, bool]:
    await _ensure_initialized()
    if _telegram_app is None:
        raise HTTPException(status_code=503, detail="Telegram app is not initialized")

    if _telegram_secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_secret != _telegram_secret:
            raise HTTPException(status_code=403, detail="Invalid telegram webhook secret")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON payload") from exc

    update = Update.de_json(payload, _telegram_app.bot)
    if update is None:
        return {"ok": True}

    await _telegram_app.process_update(update)
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    return await _handle_telegram_webhook(request)


@app.post("/webhook")
async def webhook_post(request: Request) -> dict[str, bool]:
    return await _handle_telegram_webhook(request)


@app.post("/")
async def root_post(request: Request) -> dict[str, bool]:
    return await _handle_telegram_webhook(request)


def _matches_webhook_alias(path: str) -> bool:
    normalized = path.strip("/").lower()
    if not normalized:
        return True
    if normalized.endswith("webhook"):
        return True
    return normalized in {
        "api",
        "api/index",
        "api/app",
        "api/index.py",
        "api/app.py",
    }


@app.get("/{full_path:path}")
async def webhook_get_catchall(full_path: str) -> dict[str, str]:
    if _matches_webhook_alias(full_path):
        await _ensure_initialized()
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Not Found")


@app.post("/{full_path:path}")
async def webhook_post_catchall(full_path: str, request: Request) -> dict[str, bool]:
    if _matches_webhook_alias(full_path):
        return await _handle_telegram_webhook(request)
    raise HTTPException(status_code=404, detail="Not Found")
