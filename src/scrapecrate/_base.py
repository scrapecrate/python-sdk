"""HTTP transport (sync and async), response object and API namespaces."""

from __future__ import annotations

import asyncio
import os
import random
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

from .errors import ApiError, ConnectionError, error_for

if TYPE_CHECKING:
    from ._client import AsyncScrapeCrate, ScrapeCrate

__version__ = "1.0.0"
DEFAULT_BASE_URL = "https://api.scrapecrate.com"
ENV_API_KEY = "SCRAPECRATE_API_KEY"
ENV_BASE_URL = "SCRAPECRATE_BASE_URL"
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class Response:
    """A successful API response."""

    data: Any
    meta: dict = field(default_factory=dict)
    next_cursor: str | None = None
    has_more: bool = False

    @property
    def credits_used(self) -> int:
        return int(self.meta.get("credits_used", 0))

    @property
    def credits_remaining(self) -> int:
        return int(self.meta.get("credits_remaining", 0))

    @property
    def request_id(self) -> str | None:
        return self.meta.get("request_id")

    @classmethod
    def from_body(cls, body: dict) -> Response:
        pag = body.get("pagination") or {}
        return cls(
            data=body.get("data"),
            meta=body.get("meta") or {},
            next_cursor=pag.get("next_cursor"),
            has_more=bool(pag.get("has_more")),
        )


def _clean(params: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in params.items():
        if v is None:
            continue
        out[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return out


def build_request(path: str, path_params: tuple[str, ...], params: dict[str, Any]) -> tuple[str, dict]:
    query = dict(params)
    for name in path_params:
        value = query.pop(name, None)
        if value is None:
            raise ValueError(f"missing required parameter: {name}")
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    return path, _clean(query)


def _retry_after(resp: httpx.Response) -> int | None:
    try:
        return int(resp.headers.get("Retry-After", ""))
    except ValueError:
        return None


def _backoff(attempt: int, retry_after: int | None) -> float:
    if retry_after is not None:
        return float(min(retry_after, 60))
    return min(0.5 * 2**attempt, 8.0) + random.random() * 0.25


NO_RETRY_CODES = {"not_available"}  # the API is not launched: retrying never helps


def _retryable(resp: httpx.Response) -> bool:
    if resp.status_code not in RETRY_STATUSES:
        return False
    body = _json(resp)
    code = body.get("error", {}).get("code") if isinstance(body, dict) else None
    return code not in NO_RETRY_CODES


class _Config:
    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        timeout: float,
        max_retries: int,
    ) -> None:
        self.api_key = api_key or os.environ.get(ENV_API_KEY)
        if not self.api_key:
            raise ValueError(f"No API key: pass api_key=... or set {ENV_API_KEY}")
        self.base_url = (base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key or "", "User-Agent": f"scrapecrate-python/{__version__}"}


class SyncTransport:
    def __init__(self, config: _Config, http_client: httpx.Client | None = None) -> None:
        self.config = config
        self._http = http_client or httpx.Client(timeout=config.timeout)

    def get(self, path: str, query: dict[str, str]) -> Response:
        attempt = 0
        while True:
            try:
                resp = self._http.get(self.config.base_url + path, params=query, headers=self.config.headers)
            except httpx.HTTPError as e:
                if attempt < self.config.max_retries:
                    time.sleep(_backoff(attempt, None))
                    attempt += 1
                    continue
                raise ConnectionError(0, "connection_error", str(e)) from e
            if resp.status_code == 200:
                return Response.from_body(resp.json())
            ra = _retry_after(resp)
            if _retryable(resp) and attempt < self.config.max_retries:
                time.sleep(_backoff(attempt, ra))
                attempt += 1
                continue
            raise error_for(resp.status_code, _json(resp), ra)

    def close(self) -> None:
        self._http.close()


class AsyncTransport:
    def __init__(self, config: _Config, http_client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._http = http_client or httpx.AsyncClient(timeout=config.timeout)

    async def get(self, path: str, query: dict[str, str]) -> Response:
        attempt = 0
        while True:
            try:
                resp = await self._http.get(self.config.base_url + path, params=query, headers=self.config.headers)
            except httpx.HTTPError as e:
                if attempt < self.config.max_retries:
                    await asyncio.sleep(_backoff(attempt, None))
                    attempt += 1
                    continue
                raise ConnectionError(0, "connection_error", str(e)) from e
            if resp.status_code == 200:
                return Response.from_body(resp.json())
            ra = _retry_after(resp)
            if _retryable(resp) and attempt < self.config.max_retries:
                await asyncio.sleep(_backoff(attempt, ra))
                attempt += 1
                continue
            raise error_for(resp.status_code, _json(resp), ra)

    async def close(self) -> None:
        await self._http.aclose()


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


class Namespace:
    _api = ""

    def __init__(self, client: ScrapeCrate) -> None:
        self._client = client

    def _call(self, key: str, params: dict[str, Any], extra: dict[str, Any]) -> Response:
        from ._generated import ENDPOINTS

        path, path_params, _ = ENDPOINTS[key]
        p, q = build_request(path, path_params, {**params, **extra})
        return self._client._transport.get(p, q)

    def iterate(self, method: str, **params: Any) -> Iterator[Any]:
        """Yield every item of a list endpoint, following the cursor across pages."""
        fn = getattr(self, method)
        cursor = params.pop("cursor", None)
        while True:
            page = fn(**params, cursor=cursor) if cursor else fn(**params)
            yield from page.data or []
            if not page.has_more or not page.next_cursor:
                return
            cursor = page.next_cursor


class AsyncNamespace:
    _api = ""

    def __init__(self, client: AsyncScrapeCrate) -> None:
        self._client = client

    async def _call(self, key: str, params: dict[str, Any], extra: dict[str, Any]) -> Response:
        from ._generated import ENDPOINTS

        path, path_params, _ = ENDPOINTS[key]
        p, q = build_request(path, path_params, {**params, **extra})
        return await self._client._transport.get(p, q)

    async def iterate(self, method: str, **params: Any) -> AsyncIterator[Any]:
        fn = getattr(self, method)
        cursor = params.pop("cursor", None)
        while True:
            page = await (fn(**params, cursor=cursor) if cursor else fn(**params))
            for item in page.data or []:
                yield item
            if not page.has_more or not page.next_cursor:
                return
            cursor = page.next_cursor


__all__ = ["ApiError", "Response"]
