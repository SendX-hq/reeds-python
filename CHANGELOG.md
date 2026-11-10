# Changelog

## 0.1.0 (unreleased, 2026-11-10)

The first release, for the Shipping API. Install with `pip install reeds-sdk`; import it as `reeds`.

- `Reeds` and `AsyncReeds`: the same methods, for regular code and for asyncio.
- `reeds.shipping`: coverage, quotes, deliveries (create, list, get, update, book, mark ready, cancel, label), the wallet (get, fund, transactions), invoices (list, get, PDF) and the sandbox.
- Webhooks: `client.webhooks`, or `reeds.webhooks` without credentials, verifies signatures (both secrets while you rotate one) and returns typed events; `client.webhooks.send_test()` sends a test event.
- Access tokens fetched and refreshed automatically; an `Idempotency-Key` on every `POST`, reused by retries; safe retries with `Retry-After`; cursor pagination with `for` and `async for`; one exception class per kind of failure.
- Pydantic models for every object and TypedDicts for every parameter, generated from the Shipping API's OpenAPI spec as of 2026-11-10. A response that doesn't fit its model is kept as it came, never raised as an error.
- Python 3.10 or later, httpx and Pydantic 2.
