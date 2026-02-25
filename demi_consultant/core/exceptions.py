from __future__ import annotations


class AppError(Exception):
    """Base application exception."""


class ConfigError(AppError):
    """Raised when required configuration is missing or invalid."""


class ProcessLockError(AppError):
    """Raised when another process already owns the lock file."""


class GuardrailViolation(AppError):
    """Raised when request/response is outside allowed domain."""


class EmptyResponseError(AppError):
    """Raised when model returns an empty response."""


class AIClientError(AppError):
    """Raised when OpenAI request failed after retries."""


class MetaAPIError(AppError):
    """Raised when Meta Graph API request failed."""


class PayloadValidationError(AppError):
    """Raised when incoming webhook payload is malformed."""
