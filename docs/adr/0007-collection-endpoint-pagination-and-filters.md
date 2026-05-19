# ADR 0007: Collection Endpoint Pagination and Filters

## Status

Accepted

## Context

The `/collection` endpoint serves federation entity data precomputed by the
`inmor-collection` CLI. Measured against the OpenID Federation Entity
Collection 1.0 specification (Section 3) it was incomplete: it supported only
the `entity_type` filter, returned the whole list on every call, and rejected
every other parameter with `unsupported_parameter`.

Bringing the endpoint to Section 3 conformance required pagination
(`from` / `limit` / `next`) and the `trust_mark_type`, `trust_anchor`, and
`query` filters. Several of those raised design questions whose answers were
not obvious and are worth recording.

## Decision

### Stateless pagination cursor

The `from` and `next` pagination pointers are base64url-encoded `entity_id`
values rather than server-side cursor tokens. Results are already ordered by
`entity_id` (Section 3.1.1 requires a consistent order), so the last
`entity_id` of a page is a sufficient resume point. The cursor is base64url
encoded so clients treat it as opaque, as Section 3.4.1 intends.

There is no cursor state to store or expire. The `page_not_found` error
(Section 3.4.2) is therefore raised by checking whether the decoded
`entity_id` still exists in the collection (`HEXISTS`), not by tracking which
cursors were previously issued. A cursor that is not valid base64url is a
malformed request and returns `invalid_request`.

### Single precomputed collection

`inmor-collection` walks one Trust Anchor and a walk overwrites all collection
data. The endpoint records that Trust Anchor in
`inmor:collection:trust_anchor`. A request `trust_anchor` parameter is
validated against it: a match (or an omitted parameter) is served, a mismatch
returns `invalid_request`. Per-Trust-Anchor namespaced collections were not
adopted -- they would require reworking the CLI, the key model, and the
atomic-swap logic for a multi-Trust-Anchor scenario inmor does not currently
deploy.

### Verify Trust Marks during the walk

The `trust_mark_type` filter must match only entities with a Trust Mark that
the responder has verified (Section 3.3.1-2.4.1). Verification happens in the
`inmor-collection` walker -- reusing the same `verify_trust_marks` routine
`/resolve` uses -- and only verified marks are indexed into
`inmor:collection:by_trustmark:{type}`. Verification cost is thus paid once per
walk, offline, instead of on every `/collection` request.

### Dynamic by_trustmark keys vs. ADR 0004

ADR 0004 removed the blocking Redis `KEYS` command by enumerating collection
keys from a hardcoded list. Trust mark types are dynamic URLs, so the
`by_trustmark:{type}` keys cannot be hardcoded. A registry set,
`inmor:collection:trustmark_types`, records every indexed type; the
atomic-swap logic reads it to enumerate the dynamic keys, preserving the
no-`KEYS` guarantee. Because Redis `RENAME` errors on a missing source key,
the swap first runs an `EXISTS` check and renames only the staging keys that
were actually written during the walk.

## Consequences

- Pagination is memory-bounded per request and needs no cursor garbage
  collection.
- A re-walk that removes an entity invalidates any outstanding cursor pointing
  at it; the client receives `page_not_found` and restarts, which the
  `last_updated` response field already signals as a possibility.
- The `inmor-collection` walk is slower: it now verifies every entity's Trust
  Marks, which can involve outbound HTTP. This is acceptable for an offline
  CLI and is bounded by the existing per-entity trust-mark cap.
- `/collection` serves a single Trust Anchor's view. Supporting multiple Trust
  Anchors concurrently is deferred and would supersede this ADR's
  single-collection decision.
