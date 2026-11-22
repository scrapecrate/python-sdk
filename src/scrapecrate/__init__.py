"""Official Python SDK of the ScrapeCrate API: one key for YouTube, Google Maps, Trustpilot
and Meta Ad Library data."""

from ._base import Response, __version__
from ._client import AsyncScrapeCrate, ScrapeCrate
from .errors import (
    ApiError,
    AuthenticationError,
    ConnectionError,
    InsufficientCreditsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)

__all__ = [
    "ApiError",
    "AsyncScrapeCrate",
    "AuthenticationError",
    "ConnectionError",
    "InsufficientCreditsError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "Response",
    "ScrapeCrate",
    "ServiceUnavailableError",
    "ValidationError",
    "__version__",
]
