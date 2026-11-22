"""Typed errors. Every error carries the API's code, message, request id and details."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        request_id: str | None = None,
        details: Any = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.details = details
        self.retry_after = retry_after


class ValidationError(ApiError):
    """400: a parameter is missing or invalid (see .details)."""


class AuthenticationError(ApiError):
    """401: missing or invalid API key."""


class InsufficientCreditsError(ApiError):
    """402: the balance is lower than the price of the call."""


class PermissionDeniedError(ApiError):
    """403: account disabled."""


class NotFoundError(ApiError):
    """404: the resource does not exist. Not billed."""


class RateLimitError(ApiError):
    """429: too many requests; see .retry_after."""


class ServiceUnavailableError(ApiError):
    """5xx: the data source is temporarily unavailable. Not billed; retry later."""


class ConnectionError(ApiError):
    """The API could not be reached."""


_BY_STATUS = {
    400: ValidationError,
    401: AuthenticationError,
    402: InsufficientCreditsError,
    403: PermissionDeniedError,
    404: NotFoundError,
    429: RateLimitError,
}


def error_for(status: int, body: Any, retry_after: int | None) -> ApiError:
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        err = {"code": f"http_{status}", "message": str(body)[:200] if body else ""}
    cls = _BY_STATUS.get(status) or (ServiceUnavailableError if status >= 500 else ApiError)
    return cls(
        status,
        str(err.get("code", f"http_{status}")),
        str(err.get("message", "")),
        err.get("request_id"),
        err.get("details"),
        retry_after,
    )
