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
from demi_consultant.transport.http.http_api import HTTPAPIAdapter
from demi_consultant.transport.telegram.telegram_bot import TelegramCosmoBot
from demi_consultant.transport.whatsapp.whatsapp_adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


async def _run_uvicorn(app: object, *, host: str, port: int, name: str) -> None:
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info", access_log=False) # type: ignore
    server = uvicorn.Server(config=config)
    logger.info("Starting %s webhook server on %s:%s", name, host, port)
    print(f"[INFO] uvicorn server configured for {name} at {host}:{port}")
    await server.serve()


async def run() -> None:
    print("[START] run() - loading settings")
    settings = get_settings()
    print(
        "[INFO] settings loaded: "
        f"debug={settings.debug}, "
        f"run_telegram={settings.run_telegram}, "
        f"run_whatsapp={settings.run_whatsapp}, "
        f"run_instagram={settings.run_instagram}, "
        f"run_api={settings.run_api}"
    )
    configure_logging(settings.debug)
    print("[INFO] logging configured")

    limiter = RateLimiter(interval_seconds=settings.rate_limit_seconds)
    print(f"[INFO] rate limiter created: interval_seconds={settings.rate_limit_seconds}")
    consultation_service = build_consultation_service(settings, rate_limiter=limiter)
    print("[INFO] consultation service built")

    tasks: list[asyncio.Task[None]] = []
    closers: list[tuple[str, Callable[[], Awaitable[None]]]] = []

    if settings.run_telegram:
        print("[INFO] RUN_TELEGRAM is enabled")
        if not settings.telegram_configured:
            msg = "RUN_TELEGRAM enabled, but TELEGRAM_TOKEN is missing"
            logger.warning(msg)
            print(f"[WARNING] {msg}")
        else:
            telegram_bot = TelegramCosmoBot(settings=settings, consultation_service=consultation_service)
            logger.info("Starting Telegram polling")
            print("[INFO] starting telegram polling task")
            tasks.append(asyncio.create_task(telegram_bot.run_polling()))

    if settings.run_whatsapp:
        print("[INFO] RUN_WHATSAPP is enabled")
        if not settings.whatsapp_configured:
            msg = (
                "RUN_WHATSAPP enabled, but WhatsApp credentials are incomplete "
                "(WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN/WHATSAPP_VERIFY_TOKEN)"
            )
            logger.warning(msg)
            print(f"[WARNING] {msg}")
        else:
            whatsapp_client = MetaClient(
                api_version=settings.meta_api_version,
                phone_number_id=settings.whatsapp_phone_number_id or "",
                access_token=settings.whatsapp_access_token or "",
                app_secret=settings.whatsapp_app_secret,
                timeout=settings.request_timeout_seconds,
            )
            print("[INFO] whatsapp client created")
            whatsapp_adapter = WhatsAppAdapter(
                settings=settings,
                consultation_service=consultation_service,
                meta_client=whatsapp_client,
            )
            print("[INFO] whatsapp adapter configured")
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
            print("[INFO] whatsapp uvicorn task added")
            closers.append(("whatsapp", whatsapp_client.close))

    if settings.run_instagram:
        print("[INFO] RUN_INSTAGRAM is enabled")
        if not settings.instagram_configured:
            msg = (
                "RUN_INSTAGRAM enabled, but Instagram credentials are incomplete "
                "(INSTAGRAM_ACCOUNT_ID/INSTAGRAM_ACCESS_TOKEN/INSTAGRAM_VERIFY_TOKEN)"
            )
            logger.warning(msg)
            print(f"[WARNING] {msg}")
        else:
            instagram_client = InstagramClient(
                api_version=settings.meta_api_version,
                account_id=settings.instagram_account_id or "",
                access_token=settings.instagram_access_token or "",
                app_secret=settings.instagram_app_secret,
                timeout=settings.request_timeout_seconds,
            )
            print("[INFO] instagram client created")
            instagram_adapter = InstagramAdapter(
                settings=settings,
                consultation_service=consultation_service,
                instagram_client=instagram_client,
            )
            print("[INFO] instagram adapter configured")
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
            print("[INFO] instagram uvicorn task added")
            closers.append(("instagram", instagram_client.close))

    if settings.run_api:
        print("[INFO] RUN_API is enabled")
        api_adapter = HTTPAPIAdapter(settings=settings, consultation_service=consultation_service)
        tasks.append(
            asyncio.create_task(
                _run_uvicorn(
                    api_adapter.app,
                    host=settings.api_host,
                    port=settings.api_port,
                    name="HTTP API",
                )
            )
        )
        print(f"[INFO] HTTP API task added on {settings.api_host}:{settings.api_port}")

    if not tasks:
        print("[ERROR] no tasks were started, raising ConfigError")
        raise ConfigError(
            "No channels started. Enable RUN_TELEGRAM/RUN_WHATSAPP/RUN_INSTAGRAM/RUN_API "
            "and provide required credentials."
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
        print("[INFO] shutdown requested via KeyboardInterrupt")
    except Exception as exc:
        # ensure any uncaught error is visible in stdout
        logger.exception("Unhandled exception in main")
        print("[ERROR] unhandled exception in main:", exc)
        raise


if __name__ == "__main__":
    main()
