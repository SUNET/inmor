# ADR 0005: Sanitize User Input in Redis Key Construction

## Status

Accepted

## Context

User-supplied query parameters (`trust_mark_type`, `sub`, `entity_type`) are interpolated directly into Redis key names via `format!()`. While the `redis` crate uses the RESP protocol (structured binary arrays, not raw text), so classic Redis command injection via CRLF is not possible, unsanitized input still allows:

- Control characters or null bytes making keys hard to debug and monitor
- Unbounded key length wasting Redis memory
- Accessing arbitrary Redis key patterns outside intended namespaces

These parameters appear in 5 locations across `src/lib.rs`:
- `get_collection_entities()` — `entity_type` query parameter
- `list_subordinates()` — `trust_mark_type` query parameter
- `trust_mark_status()` — `sub` and `trust_mark_type` from JWT payload
- `trust_mark_list()` — `trust_mark_type` query parameter
- `trust_mark_query()` — `sub` and `trust_mark_type` query parameters

## Decision

We add two validation functions:

1. **`validate_redis_key_input()`** — general-purpose validation that rejects empty strings, strings longer than 2048 bytes, and strings containing control characters. Applied to all user-supplied values before Redis key interpolation.

2. **`validate_entity_type()`** — strict allowlist validation against the known set of OpenID Federation entity types (`openid_provider`, `openid_relying_party`, `federation_entity`, `oauth_authorization_server`, `oauth_client`, `oauth_resource`).

Invalid inputs return HTTP 400 Bad Request with a descriptive error message.

## Consequences

- All 5 Redis key construction sites are protected against malformed input
- The `entity_type` parameter is restricted to the spec-defined set of known types
- Legitimate federation URLs (up to 2048 characters) are unaffected
- Unit tests cover rejection of control characters, empty values, over-length values, and unknown entity types
