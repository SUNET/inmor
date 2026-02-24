# ADR 0002: HTTP Request Timeouts and Connection Limits

## Status

Accepted

## Context

The `get_query()` function used bare `reqwest::get()` which creates a new
throwaway client per call with no timeout, no connection pool limit, and no
maximum response body size. A malicious federation entity could exploit this
to cause the server to hang indefinitely on slow responses, exhaust memory
with oversized response bodies, or exhaust file descriptors/connections by
triggering many concurrent resolves.

## Decision

We replace the bare `reqwest::get()` with a shared `reqwest::Client` created
once at startup via `lazy_static`, configured with:

- **Connect timeout**: 5 seconds
- **Total request timeout**: 10 seconds (connect + transfer)
- **Idle connections per host**: 10 maximum
- **Redirect limit**: 5 hops (down from reqwest's default of 10)
- **Response body size limit**: 2 MB, enforced via a two-phase check
  (Content-Length header first, then actual body size)

The shared client provides connection pooling — TCP+TLS connections to the
same host are reused across requests rather than re-established each time.

## Consequences

- Outbound federation requests fail predictably after 10 seconds instead of
  hanging indefinitely.
- Memory usage is bounded: no single response can exceed 1 MB.
- Connection pooling improves performance under concurrent load by reusing
  TCP+TLS connections.
- Federation entities with legitimately slow responses or large entity
  statements (> 1 MB) will be rejected. In practice, entity configurations
  and subordinate statements are typically a few KB.
