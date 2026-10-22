# ADR 0008: Collection Endpoint Entity Collection Draft 01

## Status

Accepted. Amends ADR 0007 (the `trust_anchor` mismatch error) and ADR 0005
(the `entity_type` allowlist no longer applies to `/collection`).

## Context

ADR 0007 brought `/collection` to the Entity Collection 1.0 draft 00. Draft 01
(13 October 2026) renamed the `ui_infos` response claim to `entity_infos`,
added the `entity_claims`, `info_claims` and `locale` parameters, allowed
`POST`, and introduced the `unsupported_claim` and `invalid_trust_anchor`
errors. It also asks (sec 5.2) that `display_name`, `description`,
`keywords`, `logo_uri`, `policy_uri` and `information_uri` be copied from the
entity's metadata, which the draft 00 walker did only partially.

## Decision

### Hard rename to `entity_infos`

Responses carry only `entity_infos`. The stored record keeps a serde alias
for `ui_infos`, so a collection written by an older walker is still served
under the new name (with its `null` placeholders dropped) until the next walk
replaces it. No deprecation period: inmor is not yet production-ready.

### Allowlisted open map for Entity Type Info

Each Entity Type Info object is stored as a JSON map rather than a fixed
struct. The walker copies the OpenID Federation sec 5.2.2 informational
claims (`display_name`, `description`, `keywords`, `contacts`, `logo_uri`,
`policy_uri`, `information_uri`, `organization_name`, `organization_uri`)
including every language-tagged variant. The allowlist keeps keys, endpoints
and other bulky metadata out of the collection. `info_claims` and `locale`
are applied per request, so a single walk serves every combination.

`display_name` falls back per language tag to `client_name`
(`openid_relying_party`, `oauth_client`) or `resource_name`
(`oauth_resource`), then to `organization_name`. The last step is not in
sec 5.2, but many entities set only `organization_name`, and dropping it
would have regressed the names the draft 00 walker returned.

### Defaults and strictness

Without `entity_claims` / `info_claims` every stored claim is returned. A
requested claim outside the supported set returns `unsupported_claim`, as the
spec requires. `locale` uses RFC 4647 basic filtering and always keeps the
untagged value.

### Unknown entity types match nothing

`entity_type` values outside `KNOWN_ENTITY_TYPES` used to be rejected with a
plain-text 400. Federations may define their own entity types and the spec
defines no error for them, so any value that is safe as a Redis key name is
accepted and an unindexed type simply yields an empty result.

### `invalid_trust_anchor`

The collection still covers a single Trust Anchor (ADR 0007). A
`trust_anchor` other than the walked one now returns 404
`invalid_trust_anchor` instead of 400 `invalid_request`.

### No trust chain validation in the walker

Sec 5.3 allows limiting the collection to entities with a valid trust chain.
The walker continues to list every entity whose own entity configuration
verifies. The response is informational (sec 6.1) and clients must resolve
the entity anyway; validating chains during the walk would duplicate
`/resolve` for little gain.

### JSON errors throughout

Every error, including storage failures (500 `server_error`) and malformed
parameters, is now the sec 3.4.2 JSON object.

## Consequences

- Clients reading `ui_infos` must switch to `entity_infos`.
- Operators should re-run `inmor-collection` after upgrading to collect the
  additional claims and populate the new `intermediates` index used by
  `/status`.
- `limit=0` is now rejected; previously it was silently raised to 1, which
  violated the "MUST NOT exceed `limit`" rule.
- `last_updated` is omitted until the first walk instead of being `0`.
