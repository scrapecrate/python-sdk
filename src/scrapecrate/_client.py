"""Clients: one namespace per API (client.youtube, client.maps, client.trustpilot, client.ads)."""

from __future__ import annotations

from typing import Any

import httpx

from ._base import AsyncTransport, Response, SyncTransport, _Config
from ._generated import (
    AdsApi,
    AsyncAdsApi,
    AsyncMapsApi,
    AsyncTrustpilotApi,
    AsyncYoutubeApi,
    MapsApi,
    TrustpilotApi,
    YoutubeApi,
)


class ScrapeCrate:
    """Synchronous client.

    >>> client = ScrapeCrate(api_key="sc_live_...")       # or set SCRAPECRATE_API_KEY
    >>> client.youtube.transcript(video_id="dQw4w9WgXcQ").data["text"]
    """

    youtube: YoutubeApi
    maps: MapsApi
    trustpilot: TrustpilotApi
    ads: AdsApi

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 90.0,
        max_retries: int = 3,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._transport = SyncTransport(_Config(api_key, base_url, timeout, max_retries), http_client)
        self.youtube = YoutubeApi(self)
        self.maps = MapsApi(self)
        self.trustpilot = TrustpilotApi(self)
        self.ads = AdsApi(self)

    def account(self) -> Response:
        """Credit balance of the account (free of charge)."""
        return self._transport.get("/v1/account", {})

    def request(self, path: str, **params: Any) -> Response:
        """Call any endpoint by path, e.g. client.request("/v1/maps/places/search", q="pizza")."""
        return self._transport.get(path, {k: str(v) for k, v in params.items() if v is not None})

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> ScrapeCrate:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncScrapeCrate:
    """Asynchronous client with the same namespaces and methods (awaitable)."""

    youtube: AsyncYoutubeApi
    maps: AsyncMapsApi
    trustpilot: AsyncTrustpilotApi
    ads: AsyncAdsApi

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 90.0,
        max_retries: int = 3,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._transport = AsyncTransport(_Config(api_key, base_url, timeout, max_retries), http_client)
        self.youtube = AsyncYoutubeApi(self)
        self.maps = AsyncMapsApi(self)
        self.trustpilot = AsyncTrustpilotApi(self)
        self.ads = AsyncAdsApi(self)

    async def account(self) -> Response:
        return await self._transport.get("/v1/account", {})

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> AsyncScrapeCrate:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
