# ADR 0001: SSRF Protection for Outbound HTTP Requests

## Status

Accepted

## Context

The Trust Anchor makes outbound HTTP requests in several code paths: the
`/resolve` endpoint (user-supplied `sub` parameter), federation tree walking,
and subordinate statement fetching. All of these flow through a single function,
`get_query()`. Prior to this change, `get_query()` passed URLs directly to
`reqwest::get()` with no validation.

An attacker could exploit this to make the server fetch internal services
(`http://127.0.0.1:6379`), cloud metadata APIs (`http://169.254.169.254/`),
or arbitrary internal URLs -- a classic Server-Side Request Forgery (SSRF)
vulnerability.

## Decision

We add a `validate_federation_url()` function called inside `get_query()` so
that **all** outbound requests pass through a single validation chokepoint.

The validation enforces:

1. **HTTPS-only scheme** -- HTTP, FTP, file, and other schemes are rejected.
2. **DNS resolution with private IP blocking** -- the hostname is resolved and
   every returned IP is checked against private, loopback, link-local, and
   unspecified ranges. If any resolved address is private, the request is
   blocked.

A configuration option `allow_http` (in `taconfig.toml`) relaxes both checks
for development use. When `allow_http = true`, HTTP scheme is permitted and
the DNS/IP check is skipped entirely. The default is `false`.

The `allow_http` flag is stored in a global `AtomicBool` set once at startup
from the parsed configuration file.

## Consequences

- Production deployments are protected against SSRF by default with no
  configuration required.
- Development environments must set `allow_http = true` in `taconfig.toml`
  to allow requests to localhost and other private addresses.
- The integration test suite sets `allow_http = true` in its generated config
  since the test server runs on localhost.
- The `url` crate is added as a direct dependency for URL parsing.
