# ScrapeCrate Python SDK

One API key for YouTube, Google Maps, Trustpilot and Meta Ad Library data.

```bash
pip install scrapecrate
```

```python
from scrapecrate import ScrapeCrate

client = ScrapeCrate(api_key="YOUR_API_KEY")  # or set SCRAPECRATE_API_KEY

t = client.youtube.transcript(video_id="dQw4w9WgXcQ", lang="en")
print(t.data["text"], t.credits_used, t.credits_remaining)

places = client.maps.places_search(q="coffee in Berlin", limit=20)
for review in client.maps.iterate("place_reviews", place_id=places.data[0]["id"], sort="newest"):
    print(review["rating"], review["text"])
```

- One namespace per API (`youtube`, `maps`, `trustpilot`, `ads`), one method per endpoint, same
  parameter names as the HTTP API. `iterate()` follows cursors.
- `AsyncScrapeCrate` has the same methods (awaitable, `async for` with `iterate`).
- Typed errors: `ValidationError`, `AuthenticationError`, `InsufficientCreditsError`,
  `PermissionDeniedError`, `NotFoundError`, `RateLimitError`, `ServiceUnavailableError` (all `ApiError`), see below.
- Retries 429/5xx with backoff (failed calls are never billed).

## Errors

Every API error arrives as `{"error": {"code", "message", "request_id", "details"?}}` and is never billed.
The SDK raises it as a typed exception with the same fields:

```python
from scrapecrate import ScrapeCrate, ApiError, NotFoundError, InsufficientCreditsError

client = ScrapeCrate()
try:
    company = client.trustpilot.company(domain="example.com").data
except NotFoundError:
    company = None                       # 404 not_found (or a specific *_not_found code)
except InsufficientCreditsError as e:
    print(e.details)                     # {"required": 3, "available": 0}
except ApiError as e:
    print(e.status, e.code, e.message, e.request_id, e.details, e.retry_after)
```

| Exception | Status | Codes |
|---|---|---|
| `ValidationError` | 400 | `invalid_parameter` (`details`: `[{"param", "message"}]`), `invalid_cursor` |
| `AuthenticationError` | 401 | `missing_api_key`, `invalid_api_key` |
| `InsufficientCreditsError` | 402 | `insufficient_credits` (`details`: `{"required", "available"}`) |
| `PermissionDeniedError` | 403 | `account_disabled` |
| `NotFoundError` | 404 | `not_found`, `*_not_found` |
| `RateLimitError` | 429 | `rate_limited`, `too_many_concurrent_requests`, `insufficient_credits_retry_later` (`retry_after` set) |
| `ServiceUnavailableError` | 5xx | `source_unavailable`, `source_busy`, `source_timeout`, `source_error`, `internal_error`, `not_available` |
| `ApiError` | other | e.g. 410 `cursor_expired`, 405 `method_not_allowed` |
| `ConnectionError` | — | the API could not be reached |

429 and 5xx answers are retried up to `max_retries` (default 3) before raising. Branch on `e.code`, not only on the
class: `not_available` (503) means the API is not launched yet and will not succeed on retry, while
`source_unavailable` is temporary. Full list: https://scrapecrate.com/docs/errors

Docs: https://scrapecrate.com/docs/sdks · API reference: https://scrapecrate.com/docs/api

## Development

The endpoint methods are generated from the catalog: `python3 sdks/generate.py` (repo root).

```bash
uv venv && uv pip install -e ".[dev]" && pytest
```
