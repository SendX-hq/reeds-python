# Changelog

## 0.2.0 (2026-11-11)

### Added

- Address search: `reeds.shipping.addresses.autocomplete(query=..., session_token=...)` for suggestions as a customer types, `details(place_id=..., session_token=...)` for the full address of the place they pick (with the `lga`, `state` and `place_id` a quote needs), and `reverse(latitude=..., longitude=...)` for the address at a map pin. On `Reeds` and `AsyncReeds`. They return `PlaceSuggestionsResult` and `Place`. Address search is free, within an allowance in Test mode; past it, or switched off by Reeds, a search raises `PermissionDeniedError` with the code `ADDRESS_SEARCH_LIMIT_REACHED` or `ADDRESS_SEARCH_DISABLED`.
- The parameter types `AddressAutocompleteParams`, `AddressDetailsParams` and `AddressReverseParams`.
- The models and parameter types follow the Shipping API's OpenAPI spec as of 2026-11-11.

### Changed

- A `float` in a query string is sent as a plain decimal (`0.00001`, never `1e-05`).

## 0.1.0 (2026-11-10)

The first release, for the Shipping API. Install with `pip install reeds-sdk`; import it as `reeds`.

- `Reeds` and `AsyncReeds`: the same methods, for regular code and for asyncio.
- `reeds.shipping`: coverage, quotes, deliveries (create, list, get, update, book, mark ready, cancel, label), the wallet (get, fund, transactions), invoices (list, get, PDF) and the sandbox.
- Webhooks: `client.webhooks`, or `reeds.webhooks` without credentials, verifies signatures (both secrets while you rotate one) and returns typed events; `client.webhooks.send_test()` sends a test event.
- Access tokens fetched and refreshed automatically; an `Idempotency-Key` on every `POST`, reused by retries; safe retries with `Retry-After`; cursor pagination with `for` and `async for`; one exception class per kind of failure.
- Pydantic models for every object and TypedDicts for every parameter, generated from the Shipping API's OpenAPI spec as of 2026-11-10. A response that doesn't fit its model is kept as it came, never raised as an error.
- Python 3.11 or later, HTTPX2 and Pydantic 2.
