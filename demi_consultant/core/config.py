from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv

from demi_consultant.core.exceptions import ConfigError


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    model_name: str
    voice_reply_model: str
    audio_transcribe_model: str
    debug: bool
    request_timeout_seconds: float
    openai_max_output_tokens: int

    max_user_text_length: int
    near_limit_text_length: int
    rate_limit_seconds: int
    image_rate_limit_seconds: int
    max_images_per_session: int
    repeat_mute_seconds: int
    abuse_window_seconds: int
    abuse_max_messages: int
    abuse_block_seconds: int
    max_context_tokens: int
    max_context_messages: int
    max_image_size_mb: int

    human_contact: str

    telegram_token: str | None
    telegram_proxy_url: str | None

    meta_api_version: str
    webhook_host: str
    webhook_port_whatsapp: int
    webhook_port_instagram: int

    whatsapp_phone_number_id: str | None
    whatsapp_access_token: str | None
    whatsapp_verify_token: str | None
    whatsapp_app_secret: str | None

    instagram_account_id: str | None
    instagram_access_token: str | None
    instagram_verify_token: str | None
    instagram_app_secret: str | None

    run_telegram: bool
    run_whatsapp: bool
    run_instagram: bool
    run_api: bool

    api_host: str
    api_port: int
    api_bearer_token: str | None

    crm_enabled: bool
    crm_storage: str
    crm_json_path: str

    @property
    def whatsapp_configured(self) -> bool:
        return bool(
            self.whatsapp_phone_number_id
            and self.whatsapp_access_token
            and self.whatsapp_verify_token
        )

    @property
    def instagram_configured(self) -> bool:
        return bool(
            self.instagram_account_id
            and self.instagram_access_token
            and self.instagram_verify_token
        )

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_token)

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        if env_file is None:
            env_file = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(dotenv_path=env_file, override=False)

        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not openai_api_key:
            raise ConfigError("OPENAI_API_KEY is required")

        model_name = os.getenv("MODEL_NAME", "gpt-5-mini").strip() or "gpt-5-mini"
        voice_reply_model = os.getenv("VOICE_REPLY_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        audio_transcribe_model = (
            os.getenv("AUDIO_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe").strip()
            or "gpt-4o-mini-transcribe"
        )
        debug = _as_bool("DEBUG", default=False)

        request_timeout_seconds = _as_float("REQUEST_TIMEOUT_SECONDS", default=25.0)
        openai_max_output_tokens = _as_int("OPENAI_MAX_OUTPUT_TOKENS", default=450)

        max_user_text_length = _as_int("MAX_USER_TEXT_LENGTH", default=150)
        near_limit_text_length = _as_int("NEAR_LIMIT_TEXT_LENGTH", default=120)
        rate_limit_seconds = _as_int("RATE_LIMIT_SECONDS", default=6)
        image_rate_limit_seconds = _as_int("IMAGE_RATE_LIMIT_SECONDS", default=20)
        max_images_per_session = _as_int("MAX_IMAGES_PER_SESSION", default=5)
        repeat_mute_seconds = _as_int("REPEAT_MUTE_SECONDS", default=30)
        abuse_window_seconds = _as_int("ABUSE_WINDOW_SECONDS", default=60)
        abuse_max_messages = _as_int("ABUSE_MAX_MESSAGES", default=10)
        abuse_block_seconds = _as_int("ABUSE_BLOCK_SECONDS", default=60)
        max_context_tokens = _as_int("MAX_CONTEXT_TOKENS", default=3000)
        max_context_messages = _as_int("MAX_CONTEXT_MESSAGES", default=6)
        max_image_size_mb = _as_int("MAX_IMAGE_SIZE_MB", default=8)

        human_contact = os.getenv("HUMAN_CONTACT", "@manager").strip() or "@manager"

        telegram_token = _or_none(os.getenv("TELEGRAM_TOKEN"))
        telegram_proxy_url = _or_none(os.getenv("TELEGRAM_PROXY_URL"))

        meta_api_version = os.getenv("META_API_VERSION", "v23.0").strip() or "v23.0"
        webhook_host = os.getenv("WEBHOOK_HOST", "0.0.0.0").strip() or "0.0.0.0"
        webhook_port_whatsapp = _as_int("WHATSAPP_WEBHOOK_PORT", default=8081)
        webhook_port_instagram = _as_int("INSTAGRAM_WEBHOOK_PORT", default=8082)

        whatsapp_phone_number_id = _or_none(os.getenv("WHATSAPP_PHONE_NUMBER_ID"))
        whatsapp_access_token = _or_none(os.getenv("WHATSAPP_ACCESS_TOKEN"))
        whatsapp_verify_token = _or_none(os.getenv("WHATSAPP_VERIFY_TOKEN"))
        whatsapp_app_secret = _or_none(os.getenv("WHATSAPP_APP_SECRET"))

        instagram_account_id = _or_none(os.getenv("INSTAGRAM_ACCOUNT_ID"))
        instagram_access_token = _or_none(os.getenv("INSTAGRAM_ACCESS_TOKEN"))
        instagram_verify_token = _or_none(os.getenv("INSTAGRAM_VERIFY_TOKEN"))
        instagram_app_secret = _or_none(os.getenv("INSTAGRAM_APP_SECRET"))

        run_telegram = _as_bool("RUN_TELEGRAM", default=True)
        run_whatsapp = _as_bool("RUN_WHATSAPP", default=False)
        run_instagram = _as_bool("RUN_INSTAGRAM", default=False)
        run_api = _as_bool("RUN_API", default=False)

        api_host = os.getenv("API_HOST", "0.0.0.0").strip() or "0.0.0.0"
        api_port = _as_int("API_PORT", default=8090)
        api_bearer_token = _or_none(os.getenv("API_BEARER_TOKEN"))

        crm_enabled = _as_bool("CRM_ENABLED", default=True)
        crm_storage = os.getenv("CRM_STORAGE", "memory").strip().lower() or "memory"
        if crm_storage not in {"memory", "json", "postgres"}:
            raise ConfigError("CRM_STORAGE must be one of: memory, json, postgres")
        crm_json_path = os.getenv("CRM_JSON_PATH", "./data/crm_events.json").strip() or "./data/crm_events.json"

        return cls(
            openai_api_key=openai_api_key,
            model_name=model_name,
            voice_reply_model=voice_reply_model,
            audio_transcribe_model=audio_transcribe_model,
            debug=debug,
            request_timeout_seconds=request_timeout_seconds,
            openai_max_output_tokens=openai_max_output_tokens,
            max_user_text_length=max_user_text_length,
            near_limit_text_length=near_limit_text_length,
            rate_limit_seconds=rate_limit_seconds,
            image_rate_limit_seconds=image_rate_limit_seconds,
            max_images_per_session=max_images_per_session,
            repeat_mute_seconds=repeat_mute_seconds,
            abuse_window_seconds=abuse_window_seconds,
            abuse_max_messages=abuse_max_messages,
            abuse_block_seconds=abuse_block_seconds,
            max_context_tokens=max_context_tokens,
            max_context_messages=max_context_messages,
            max_image_size_mb=max_image_size_mb,
            human_contact=human_contact,
            telegram_token=telegram_token,
            telegram_proxy_url=telegram_proxy_url,
            meta_api_version=meta_api_version,
            webhook_host=webhook_host,
            webhook_port_whatsapp=webhook_port_whatsapp,
            webhook_port_instagram=webhook_port_instagram,
            whatsapp_phone_number_id=whatsapp_phone_number_id,
            whatsapp_access_token=whatsapp_access_token,
            whatsapp_verify_token=whatsapp_verify_token,
            whatsapp_app_secret=whatsapp_app_secret,
            instagram_account_id=instagram_account_id,
            instagram_access_token=instagram_access_token,
            instagram_verify_token=instagram_verify_token,
            instagram_app_secret=instagram_app_secret,
            run_telegram=run_telegram,
            run_whatsapp=run_whatsapp,
            run_instagram=run_instagram,
            run_api=run_api,
            api_host=api_host,
            api_port=api_port,
            api_bearer_token=api_bearer_token,
            crm_enabled=crm_enabled,
            crm_storage=crm_storage,
            crm_json_path=crm_json_path,
        )


def _or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _as_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
