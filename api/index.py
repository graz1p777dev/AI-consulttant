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

        vercel_url = os.getenv("VERCEL_PROJECT_PRODUCTION_URL") or os.getenv("VERCEL_URL")
        if vercel_url:
            webhook_url = f"https://{vercel_url}/telegram/webhook"
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


@app.get("/telegram/webhook")
async def telegram_webhook_get() -> dict[str, str]:
    await _ensure_initialized()
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
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
