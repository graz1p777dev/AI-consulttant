from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from fastapi import FastAPI

from demi_consultant.bootstrap import build_consultation_service
from demi_consultant.core.config import get_settings
from demi_consultant.core.logger import configure_logging
from demi_consultant.integrations.meta_api.instagram_client import InstagramClient
from demi_consultant.integrations.meta_api.meta_client import MetaClient
from demi_consultant.transport.instagram.instagram_adapter import InstagramAdapter
from demi_consultant.transport.rate_limit import RateLimiter
from demi_consultant.transport.whatsapp.whatsapp_adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


@dataclass
class _RuntimeClients:
    whatsapp: MetaClient | None = None
    instagram: InstagramClient | None = None


def _build_runtime_app() -> tuple[FastAPI, _RuntimeClients]:
    settings = get_settings()
    configure_logging(settings.debug)

    limiter = RateLimiter(interval_seconds=settings.rate_limit_seconds)
    consultation_service = build_consultation_service(settings, rate_limiter=limiter)
    clients = _RuntimeClients()

    api_app = FastAPI(title="Demi Consultant API")

    @api_app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if settings.run_whatsapp and settings.whatsapp_configured:
        clients.whatsapp = MetaClient(
            api_version=settings.meta_api_version,
            phone_number_id=settings.whatsapp_phone_number_id or "",
            access_token=settings.whatsapp_access_token or "",
            app_secret=settings.whatsapp_app_secret,
            timeout=settings.request_timeout_seconds,
        )
        whatsapp_adapter = WhatsAppAdapter(
            settings=settings,
            consultation_service=consultation_service,
            meta_client=clients.whatsapp,
        )
        api_app.mount("/whatsapp", whatsapp_adapter.app)
    elif settings.run_whatsapp:
        logger.warning(
            "RUN_WHATSAPP enabled, but WhatsApp credentials are incomplete "
            "(WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN/WHATSAPP_VERIFY_TOKEN)"
        )

    if settings.run_instagram and settings.instagram_configured:
        clients.instagram = InstagramClient(
            api_version=settings.meta_api_version,
            account_id=settings.instagram_account_id or "",
            access_token=settings.instagram_access_token or "",
            app_secret=settings.instagram_app_secret,
            timeout=settings.request_timeout_seconds,
        )
        instagram_adapter = InstagramAdapter(
            settings=settings,
            consultation_service=consultation_service,
            instagram_client=clients.instagram,
        )
        api_app.mount("/instagram", instagram_adapter.app)
    elif settings.run_instagram:
        logger.warning(
            "RUN_INSTAGRAM enabled, but Instagram credentials are incomplete "
            "(INSTAGRAM_ACCOUNT_ID/INSTAGRAM_ACCESS_TOKEN/INSTAGRAM_VERIFY_TOKEN)"
        )

    return api_app, clients


app = FastAPI(title="Demi Consultant Vercel")
_clients = _RuntimeClients()
_initialized = False
_init_lock = asyncio.Lock()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _ensure_initialized() -> None:
    global _initialized, _clients
    if _initialized:
        return

    async with _init_lock:
        if _initialized:
            return
        runtime_app, _clients = _build_runtime_app()
        app.mount("/", runtime_app)
        _initialized = True


@app.on_event("startup")
async def _startup() -> None:
    await _ensure_initialized()


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _clients.whatsapp is not None:
        await _clients.whatsapp.close()
    if _clients.instagram is not None:
        await _clients.instagram.close()
