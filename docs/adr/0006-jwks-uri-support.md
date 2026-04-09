# ADR 0006: Support `jwks_uri` for Remote Federation Key Retrieval

## Status

Accepted

## Context

The system previously required inline `jwks` claims in all entity configurations. Every function that needed an entity's public keys — self-verification, trust chain resolution (`/resolve`), and federation tree walking (`inmor-collection`) — extracted keys from `payload.claim("jwks")` and failed if the claim was absent.

In practice, many federation entities publish their keys via `jwks_uri` (a URL pointing to a JWKS document) instead of embedding keys inline. The OpenID Federation 1.0 specification also defines `signed_jwks_uri` for a cryptographically signed variant. Without support for these, the Trust Anchor could not:

- Resolve trust chains through intermediates that use `jwks_uri`
- Walk federation trees containing entities without inline keys
- Register subordinates whose entity configurations omit inline `jwks`

On the Python side, `self_validate()` crashed with an `AttributeError` when `jwks` was `None`, since it called `.get("keys")` on `None`.

### Spec Clarification

Per OpenID Federation 1.0 Section 5.2.1, `jwks_uri` and `signed_jwks_uri` are metadata-level parameters (inside `metadata.openid_provider.*` etc.), not top-level entity statement claims. The top-level `jwks` is REQUIRED for entity statements. `signed_jwks_uri` is specifically for protocol keys (OP/RP) and requires signature verification using federation entity keys — it does not apply to federation key retrieval. Our implementation therefore only falls back to `jwks_uri` as a defensive measure for non-compliant entities, while the inline `jwks` path remains the primary and spec-compliant path.

## Decision

We add a two-level fallback chain: **inline `jwks` → `jwks_uri`**.

### Rust (`src/lib.rs`)

- **`fetch_jwks_from_uri(uri)`** — fetches a JWKS document from a remote URI using the existing shared HTTP client, with the same URL validation (SSRF protection, HTTPS enforcement) and response size limits as other federation requests.

- **`parse_jwks_json(json_str)`** — shared helper to parse a JWKS JSON string into a `JwkSet`.

- **`get_jwks_from_uri_cached(uri, redis_conn)`** — wraps `fetch_jwks_from_uri` with Redis-backed caching. Cache key: `inmor:jwks_cache:{sha256(uri)}`, TTL: 1 hour. Avoids repeated network round-trips during chain resolution.

- **`get_jwks_from_payload_or_uri(payload, redis_conn)`** — the main entry point. Tries `get_jwks_from_payload()` first (inline keys), falls back to `jwks_uri` via `get_jwks_from_uri_cached()`.

- **`resolve_entity_to_trustanchor()`** — updated to accept a `redis::aio::ConnectionManager` parameter and use `get_jwks_from_payload_or_uri()` instead of `get_jwks_from_payload()` when obtaining authority keys for subordinate statement verification.

### Rust (`src/tree.rs`)

- **`collection_tree_walking()`** and **`fetch_all_subordinate_statements()`** — when `self_verify_jwt()` fails, the code now extracts the unverified payload, attempts `get_jwks_from_payload_or_uri()` to fetch keys, and retries verification with the fetched keyset.

### Python (`admin/entities/lib.py`)

- **`fetch_jwks_from_uri(uri)`** — fetches a JWKS document via `httpx`.

- **`self_validate()`** — fixed the `AttributeError` crash. Now checks for inline `jwks` first, falls back to `jwks_uri` (via `fetch_jwks_from_uri`). Raises a clear `ValueError` if neither is present.

### Python (`admin/inmoradmin/api.py`)

- **`FetchConfigOutSchema`** — added optional `jwks_uri` field so the fetch-config endpoint returns it when present. The endpoint also resolves `jwks_uri` into inline keys server-side so the frontend always receives populated `jwks`.

### Why not `signed_jwks_uri`?

Per OpenID Federation 1.0 Section 5.2.1, `signed_jwks_uri` is a metadata-level parameter for protocol keys (e.g., OP/RP keys under `metadata.openid_provider`). It requires signature verification using the entity's Federation Entity Keys. Since this implementation deals exclusively with federation key retrieval (top-level `jwks`), `signed_jwks_uri` does not apply — the top-level `jwks` is REQUIRED per spec, and `jwks_uri` is the only meaningful fallback for federation keys.

### Caching Strategy

JWKS responses are cached in Redis rather than in-process memory because the Rust server runs behind actix-web with multiple worker threads sharing the same Redis connection. A 1-hour TTL balances freshness (key rotation is infrequent in federation) against avoiding per-request latency. The Python side does not cache JWKS responses yet; this can be added via Django's cache framework if needed.

## Consequences

- Trust chain resolution now works through entities that publish `jwks_uri` instead of inline `jwks`
- Federation tree walking discovers entities that were previously skipped due to missing inline keys
- The `self_validate()` crash on missing `jwks` is fixed with a clear error path
- JWKS fetches reuse the existing SSRF-protected HTTP client — no new attack surface
- Redis stores cached JWKS with automatic expiry, avoiding stale keys and unbounded growth
- The fallback chain is consistent across Rust and Python: `jwks` → `jwks_uri`
