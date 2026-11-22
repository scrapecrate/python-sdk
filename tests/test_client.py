"""SDK tests against an in-memory fake of the public API (httpx.MockTransport)."""

from __future__ import annotations

import json

import httpx
import pytest

from scrapecrate import (
    AsyncScrapeCrate,
    AuthenticationError,
    InsufficientCreditsError,
    NotFoundError,
    ScrapeCrate,
    ServiceUnavailableError,
    ValidationError,
)
from scrapecrate._generated import ENDPOINTS


def ok(data, cursor=None, used=1, remaining=99, has_more=None):
    body = {"data": data, "meta": {"request_id": "req_1", "credits_used": used, "credits_remaining": remaining}}
    if isinstance(data, list):
        body["pagination"] = {"next_cursor": cursor, "has_more": cursor is not None if has_more is None else has_more}
    return httpx.Response(200, json=body)


def err(status, code, **extra):
    return httpx.Response(status, json={"error": {"code": code, "message": code, "request_id": "req_e", **extra}})


class Fake:
    def __init__(self, handler):
        self.calls: list[httpx.Request] = []
        self.handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


def client_with(handler, **kw):
    fake = Fake(handler)
    c = ScrapeCrate(
        api_key="sc_test",
        base_url="https://api.test",
        http_client=httpx.Client(transport=httpx.MockTransport(fake)),
        **kw,
    )
    return c, fake


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("SCRAPECRATE_API_KEY", raising=False)
    with pytest.raises(ValueError):
        ScrapeCrate()


def test_env_api_key(monkeypatch):
    monkeypatch.setenv("SCRAPECRATE_API_KEY", "sc_env")
    assert ScrapeCrate()._transport.config.api_key == "sc_env"


def test_call_builds_path_query_and_headers():
    c, fake = client_with(lambda r: ok({"video_id": "abc"}))
    res = c.youtube.transcript(video_id="dQw4w9WgXcQ", lang="it")
    req = fake.calls[0]
    assert req.url.path == "/v1/youtube/transcripts/dQw4w9WgXcQ"
    assert dict(req.url.params) == {"lang": "it"}
    assert req.headers["X-API-Key"] == "sc_test"
    assert res.data == {"video_id": "abc"} and res.credits_used == 1 and res.credits_remaining == 99
    assert res.request_id == "req_1"


def test_booleans_and_path_escaping():
    c, fake = client_with(lambda r: ok([]))
    c.trustpilot.company_reviews(domain="a.com/x", verified=True, limit=5)
    req = fake.calls[0]
    assert req.url.raw_path.startswith(b"/v1/trustpilot/companies/a.com%2Fx/reviews")
    assert dict(req.url.params) == {"verified": "true", "limit": "5"}


def test_every_catalog_endpoint_has_a_method():
    c, fake = client_with(lambda r: ok({}))
    for key in ENDPOINTS:
        api, method = key.split(".")
        assert callable(getattr(getattr(c, api), method)), key


def test_iterate_follows_cursor():
    pages = {None: (["a", "b"], "c2"), "c2": (["c"], None)}

    def handler(r):
        items, nxt = pages[r.url.params.get("cursor")]
        return ok(items, nxt)

    c, fake = client_with(handler)
    assert list(c.maps.iterate("place_reviews", place_id="p1", limit=2)) == ["a", "b", "c"]
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "status,code,exc",
    [
        (400, "invalid_parameter", ValidationError),
        (401, "invalid_api_key", AuthenticationError),
        (402, "insufficient_credits", InsufficientCreditsError),
        (404, "not_found", NotFoundError),
    ],
)
def test_errors(status, code, exc):
    c, _ = client_with(lambda r: err(status, code, details={"x": 1}))
    with pytest.raises(exc) as ei:
        c.ads.ad(ad_id="123456")
    assert ei.value.code == code and ei.value.request_id == "req_e" and ei.value.details == {"x": 1}


def test_retries_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr("scrapecrate._base._backoff", lambda a, r: 0)
    responses = iter([err(503, "source_unavailable"), err(429, "rate_limited"), ok({"ok": True})])
    c, fake = client_with(lambda r: next(responses))
    assert c.maps.place(place_id="p").data == {"ok": True}
    assert len(fake.calls) == 3


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("scrapecrate._base._backoff", lambda a, r: 0)
    c, fake = client_with(lambda r: err(503, "source_unavailable"), max_retries=2)
    with pytest.raises(ServiceUnavailableError):
        c.maps.place(place_id="p")
    assert len(fake.calls) == 3


def test_no_retry_on_4xx():
    c, fake = client_with(lambda r: err(404, "not_found"))
    with pytest.raises(NotFoundError):
        c.youtube.video(video_id="x")
    assert len(fake.calls) == 1


def test_account():
    c, fake = client_with(lambda r: httpx.Response(200, json={"data": {"credits_remaining": 5}}))
    assert c.account().data["credits_remaining"] == 5
    assert fake.calls[0].url.path == "/v1/account"


async def test_async_client():
    pages = {None: ([1, 2], "n"), "n": ([3], None)}

    def handler(r):
        items, nxt = pages[r.url.params.get("cursor")]
        return ok(items, nxt)

    async with AsyncScrapeCrate(
        api_key="k", base_url="https://api.test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ) as c:
        res = await c.ads.ads_search(q="shoes")
        assert res.data == [1, 2] and res.next_cursor == "n"
        items = [i async for i in c.ads.iterate("ads_search", q="shoes")]
        assert items == [1, 2, 3]


def test_no_private_names_in_package():
    import pathlib

    import scrapecrate

    text = "".join(p.read_text() for p in pathlib.Path(scrapecrate.__file__).parent.glob("*.py")).lower()
    for w in ("fetch" "transcript", "satellite", "upstream", "internal/v1"):
        assert w not in text
    assert json.dumps(ENDPOINTS)


def test_no_retry_when_api_not_available():
    c, fake = client_with(lambda r: err(503, "not_available"))
    with pytest.raises(ServiceUnavailableError):
        c.maps.place(place_id="p")
    assert len(fake.calls) == 1
