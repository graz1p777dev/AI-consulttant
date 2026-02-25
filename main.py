from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import uvicorn

from demi_consultant.bootstrap import build_consultation_service
from demi_consultant.core.config import get_settings
from demi_consultant.core.exceptions import ConfigError
from demi_consultant.core.logger import configure_logging
from demi_consultant.integrations.meta_api.instagram_client import InstagramClient
from demi_consultant.integrations.meta_api.meta_client import MetaClient
from demi_consultant.transport.instagram.instagram_adapter import InstagramAdapter
from demi_consultant.transport.rate_limit import RateLimiter
from demi_consultant.transport.telegram.telegram_bot import TelegramCosmoBot
from demi_consultant.transport.whatsapp.whatsapp_adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


async def _run_uvicorn(app: object, *, host: str, port: int, name: str) -> None:
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info", access_log=False) # type: ignore
    server = uvicorn.Server(config=config)
    logger.info("Starting %s webhook server on %s:%s", name, host, port)
    await server.serve()


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.debug)

    limiter = RateLimiter(interval_seconds=settings.rate_limit_seconds)
    consultation_service = build_consultation_service(settings, rate_limiter=limiter)

    tasks: list[asyncio.Task[None]] = []
    closers: list[tuple[str, Callable[[], Awaitable[None]]]] = []

    if settings.run_telegram:
        if not settings.telegram_configured:
            logger.warning("RUN_TELEGRAM enabled, but TELEGRAM_TOKEN is missing")
        else:
            telegram_bot = TelegramCosmoBot(settings=settings, consultation_service=consultation_service)
            logger.info("Starting Telegram polling")
            tasks.append(asyncio.create_task(telegram_bot.run_polling()))

    if settings.run_whatsapp:
        if not settings.whatsapp_configured:
            logger.warning(
                "RUN_WHATSAPP enabled, but WhatsApp credentials are incomplete "
                "(WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN/WHATSAPP_VERIFY_TOKEN)"
            )
        else:
            whatsapp_client = MetaClient(
                api_version=settings.meta_api_version,
                phone_number_id=settings.whatsapp_phone_number_id or "",
                access_token=settings.whatsapp_access_token or "",
                app_secret=settings.whatsapp_app_secret,
                timeout=settings.request_timeout_seconds,
            )
            whatsapp_adapter = WhatsAppAdapter(
                settings=settings,
                consultation_service=consultation_service,
                meta_client=whatsapp_client,
            )
            tasks.append(
                asyncio.create_task(
                    _run_uvicorn(
                        whatsapp_adapter.app,
                        host=settings.webhook_host,
                        port=settings.webhook_port_whatsapp,
                        name="WhatsApp",
                    )
                )
            )
            closers.append(("whatsapp", whatsapp_client.close))

    if settings.run_instagram:
        if not settings.instagram_configured:
            logger.warning(
                "RUN_INSTAGRAM enabled, but Instagram credentials are incomplete "
                "(INSTAGRAM_ACCOUNT_ID/INSTAGRAM_ACCESS_TOKEN/INSTAGRAM_VERIFY_TOKEN)"
            )
        else:
            instagram_client = InstagramClient(
                api_version=settings.meta_api_version,
                account_id=settings.instagram_account_id or "",
                access_token=settings.instagram_access_token or "",
                app_secret=settings.instagram_app_secret,
                timeout=settings.request_timeout_seconds,
            )
            instagram_adapter = InstagramAdapter(
                settings=settings,
                consultation_service=consultation_service,
                instagram_client=instagram_client,
            )
            tasks.append(
                asyncio.create_task(
                    _run_uvicorn(
                        instagram_adapter.app,
                        host=settings.webhook_host,
                        port=settings.webhook_port_instagram,
                        name="Instagram",
                    )
                )
            )
            closers.append(("instagram", instagram_client.close))

    if not tasks:
        raise ConfigError(
            "No channels started. Enable RUN_TELEGRAM/RUN_WHATSAPP/RUN_INSTAGRAM "
            "and provide channel credentials."
        )

    try:
        await asyncio.gather(*tasks)
    finally:
        for name, close_fn in closers:
            try:
                await close_fn()
            except Exception:
                logger.exception("Failed to close %s client", name)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")


if __name__ == "__main__":
    main()
