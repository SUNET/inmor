
<a id='changelog-0.5.0'></a>
# 0.5.0 - 2026-10-22

## Security

- Root CA incident: the Admin and test environments use certifi 2026.10.19,
  which removes "emSign ECC Root CA - G3" in line with Debian's
  `ca-certificates` 20250419+deb13u1. It is taken inside the dependency
  cooling window as an explicit, documented exception. The TA trusts the
  system CA store (OpenSSL via native-tls), and both runtime images pick up
  the Debian update through `apt dist-upgrade`: rebuild the 0.5.0 images
  with `--pull --no-cache` so a cached layer does not keep the old roots.
- The TA no longer compiles actix-web's HTTP/2 server, which depends on h2
  0.3 with no fix for RUSTSEC-2026-0258 (unbounded empty DATA frames). The
  TA's own TLS listener now serves HTTP/1.1 only; reverse proxies can still
  offer HTTP/2 to clients.
- `.cargo/audit.toml` records the known `rustls-pemfile` unmaintained
  advisory (RUSTSEC-2025-0134), so `cargo audit` passes.

## Breaking changes

- The Admin now runs on Django 6.1 and continues to require Python 3.13.
- All bundled Docker Compose configurations now use PostgreSQL 15 instead of
  PostgreSQL 14. Existing database volumes must be backed up and converted with
  `pg_upgrade` before this version is started; see
  `docs/postgresql-upgrade.rst` for the named-volume and development
  bind-mount procedures.
- The `/collection` endpoint follows the OpenID Federation Entity Collection
  1.0 draft 01. The response claim `ui_infos` is renamed `entity_infos`; a
  `trust_anchor` other than the collected one returns 404
  `invalid_trust_anchor` instead of 400 `invalid_request`; `limit=0` is
  rejected; and `last_updated` is omitted until the first walk. Re-run
  `inmor-collection` after upgrading to collect the additional entity
  information (see ADR 0008).

## Added

- `/collection` accepts `POST` with a form-urlencoded body and the
  `entity_claims`, `info_claims` and `locale` parameters, returning
  `unsupported_claim` for unsupported claims.
- The collection walker now collects `description`, `keywords`, `contacts`,
  `information_uri`, `organization_name`, `organization_uri` and
  language-tagged variants, using the metadata `display_name` with the
  spec sec 5.2 fallbacks.
- Admin API `GET /api/v1/server/collection` and an Entity Collection card on
  the Admin dashboard.

## Changed

- Updated all Rust dependencies, including the semver-major bumps
  actix-web-lab 0.29, base64 0.23, redis 1.7, reqwest 0.13, sha2 0.11,
  tera 2.4 and toml 1.1. reqwest stays on native-tls (its 0.13 default is
  rustls) so outbound requests keep using the system CA store. Crates
  published after 2026-10-19 UTC are held back to their previous release
  for a three-day cooling period.
- The index page templates moved from Tera macros to Tera 2 components.
- Updated all Python dependencies with the `exclude-newer` cutoff moved to
  2026-10-19 UTC in both projects. The pygamlastan-specific cutoff is no
  longer needed and was removed.
- All compose files and the deployment docs reference the 0.5.0 images. The
  root `docker-compose.yml` bind-mounts `./templates`, which now use Tera 2
  component syntax that older TA images cannot load.
- New `docs/releasing.rst` lists every place the release version must be
  updated, and `just check-version` (run by `just lint` and CI) fails when any
  of them disagrees with `Cargo.toml`.
- Pinned the root project's Ruff rule set (`E4`, `E7`, `E9`, `F`), as the
  Admin already does, so Ruff upgrades do not change the lint rules.

- Refreshed and relocked all Admin Python dependencies using a fixed
  2026-08-24 UTC `exclude-newer` cutoff, providing a three-day package cooling
  period at update time.
- Replaced PySAML2 with pygamlastan 0.6.0 through the djangosaml2
  `feat/pygamlastan` fork, pinned to commit
  `5ba29b5f97ae6a6f0aba877ffbadf1c299de18c7` in both dependency manifests.
  The pygamlastan-specific cutoff is 2026-09-21 UTC, preserving a three-day
  cooling period at the September 24 update.
- Python setup and test recipes now use the checked-in uv lock file. Ruff keeps
  its historical default rule set explicit, while new pre-1.0 ty diagnostics
  remain visible as warnings.
- CI now tests with Python 3.13 and PostgreSQL 15 and uses the dynamically
  published PostgreSQL service port.
- Updated the Admin's generated settings, URL, ASGI, and WSGI documentation
  references for Django 6.1.

## Fixed

- `/collection` errors are always JSON, including unknown `entity_type`
  values (which now match nothing instead of failing), malformed parameters
  and Redis failures (500 `server_error`).
- `/status` `collection.intermediates` counted every entity; it now counts
  only Intermediates below the Trust Anchor.
- The collection staging-to-live swap now runs in `MULTI`/`EXEC`, so readers
  never observe a half-swapped collection.
- `/collection` reads a page of records with a single `HMGET`.
- `/collection` validates `locale` against the RFC 4647 basic language range
  grammar (long valid ranges were rejected, `123` accepted), and an unreadable
  or oversized `POST` body gets the JSON error object instead of plain text.
- The collection walker compares language tags case-insensitively when
  filling `display_name` fallbacks, so `client_name#sv-se` no longer adds a
  second Swedish name next to `display_name#sv-SE`.
- Only a string `federation_list_endpoint` marks an entity as an Intermediate;
  a `null` or other non-string value is a leaf, matching subordinate
  discovery, so `/status` and the Admin statistics no longer over-count.
- A failed write to the collection Intermediate index now aborts the walk
  before publication, like trust mark index failures, instead of publishing
  an undercount to `/status` and the Admin statistics.
- `just lint-frontend` now type-checks the frontend (`vue-tsc -b`); the old
  `vue-tsc --noEmit` checked no files. It runs as part of `just lint` and CI.

- The API-key validity column in Django Admin now supplies interpolation
  arguments to `format_html()`, as required by Django 6, instead of raising a
  `TypeError` while rendering the list page.
- Corrected the Trust Anchor build step label and PostgreSQL service-port
  expression in the GitHub Actions workflow.

<a id='changelog-0.4.1'></a>
# 0.4.1 — 2026-05-28

## Added

- `inmor-keygeneration` CLI binary that generates a Trust Anchor signing
  keypair (`private.json` + `publickeys/{kid}.json`). Bundled in the TA
  image so an operator can bootstrap keys in production without the
  source tree #242.

## Fixed

- `GET /api/v1/auditlog/{id}` now returns the full
  `snapshot_before`/`snapshot_after` pair. The detail response was
  wired to the summary schema and silently omitted the snapshots its
  docstring promised.

<a id='changelog-0.4.0'></a>
# 0.4.0 — 2026-05-21

## Added

- `/collection` endpoint upgraded to OpenID Federation Entity
  Collection 1.0 (Section 3) conformance: `from`/`limit`/`next`
  pagination, plus `trust_mark_type` (AND), `trust_anchor`, and
  `query` filters alongside the existing `entity_type` (OR) filter.
  Spec-aligned error codes (`unsupported_parameter`,
  `invalid_request`, `page_not_found`) are returned with the
  appropriate HTTP status #233.
- `inmor-collection` walker now verifies every entity's Trust Marks
  against the walk-from Trust Anchor before indexing them, populating
  `inmor:collection:by_trustmark:{type}` so the new
  `trust_mark_type` filter resolves only verified marks #233.
- Trust Mark verification in `/resolve`: returned marks are filtered
  against `trust_mark_issuers` and `trust_mark_owners` on the Trust
  Anchor's Entity Configuration.
- Consume-side Trust Mark Delegation support (spec sec 7.2):
  `delegation` JWTs are verified against the pinned owner and the
  delegated mark is accepted only when issuer, subject, expiry, and
  the `trust_mark_id`/`trust_mark_type` linkage all check out #232.
- `jwks_uri` / `signed_jwks_uri` support across the Trust Anchor and
  Admin: Entity Configurations that publish their federation keys by
  reference (rather than inline `jwks`) are now fetched, verified,
  and cached in Redis #227.
- Spec section 3/4/5 conformance: closed the remaining gaps from the
  features matrix in `features_from_spec1.0.html` #231.
- `inmor-collection` CLI accepts a Trust Anchor URL argument so a
  walk can be aimed at any federation, not just the local TA.
- `/health` liveness probe (used by the Docker healthcheck) and
  `/status` operational endpoint with key/subordinate/trust-mark
  counts.
- `just logs` recipe.

## Fixed

- Reject `alg: none` and unsupported critical (`crit`) header
  claims when verifying federation JWTs.
- Trust Mark verification: outer/inner `trust_mark_type` must match
  (spec sec 7.4); marks that fail this check are dropped.
- `/resolve` and the collection walker fall back to `jwks_uri` when
  self-verification with inline JWKS fails, so Trust Anchors that
  publish their keys only by reference are usable.
- Several security audit findings: command injection guards on
  federation-supplied strings used in Redis key names, length /
  control-char validation of trust mark types before they're
  written verbatim into Redis keys.
- Critical Redis writes in the collection walker
  (`inmor:collection:staging:trust_anchor`,
  `by_trustmark:{type}` / `trustmark_types`) now propagate or are
  counted; the atomic swap is aborted if any trust-mark index write
  failed, so a silently incomplete collection is never published.
- `/collection` distinguishes "backend error" from "no data": Redis
  failures during cursor validation, set membership, and ZSET range
  reads return `500` instead of an empty `200` or a misleading
  `404 page_not_found`.
- `/collection` `last_updated` always serializes as a number
  (defaults to `0` when no walk has run) instead of `null`.
- Pagination `next` cursor is anchored on the last entity actually
  returned, so a missing hash record can't yield a cursor that
  points at an entity not in the response.

## Changed

- `/collection` pagination is now backed by `ZRANGEBYLEX` over
  `inmor:collection:all_sorted` when no filter is active, so a
  single page no longer loads or sorts the whole id set.
- `query_matches` accepts a precomputed lowercase needle so the
  request `query` string is lowercased once per request instead of
  once per entity.

## Added

- POST /subordinates/fetch-config API endpoint to fetch and
self-validate OpenID Federation entity configurations
- Handle network errors gracefully (DNS failures, timeouts, 404s,
    invalid JWTs) with user-friendly error messages

- Frontend for the Admins
- JSON editor for all JSON fields
- API_KEYS for API access #122.
- MFA support #123

- Management commands for Trust Mark Types and Subordinates
- Enforce `kid` header in Trust Anchor JWT verification #150
- Migrate Subordinate metadata/jwks fields from CharField to JSONField #158

- Refetch metadata button to the frontend #164

- renewal API and frontend update #166

- Adds /collection endpoint back #170

- Management command for subordinate renewal #174

- apikey management command #178
- production docker compose #137
- granian to run admin django application #61

## Fixed

- Explicitly reject `alg: none` in JWT verification #151
- /trust_mark_list returns JSON error responses instead of plain text #148
- /fetch returns 400 instead of 500 on invalid entity configuration #147
- /list with trust_marked=false no longer incorrectly filters subordinates #146
- Authenticated API calls pass credentials correctly #152
- Minimal `exp` claim handling in trust mark JWTs #145

- don't include null metadata in policy document

- pass correct policy object to apply_policy and upgrade oidfpolicy to 0.2.0 #185
- `/list` endpoint fix #187
<a id='changelog-0.2.2'></a>
# 0.2.2 — 2026-02-06

## Fixed

- Fixes #144, `typ` and claim name is correct the trustmark endpoints.


<a id='changelog-0.2.1'></a>
# 0.2.1 — 2026-02-05

## Fixed

- TA bind address: Fixed the TA server bind address when TLS is not configured (#136).
- Docker: Fixed missing common module in admin container and corrected version tags in docker-compose.yml.

<a id='changelog-0.2.0'></a>
# 0.2.0 — 2026-01-12

## Removed

- `policy_document.metadata` from `settings.py`

## Added

- TA picks up public keys from `./publickeys` directory #40
- `admin` picks up public keys from `./publickeys` directory #40
- BREAKING CHANGE

- Allows TrustMarks for the TA itself. #86

- Allows `trust_mark_type` in `/list` endpoint #42

- Applying any forced metadata in subordinate statement #95.
- TA now applies metadata from authoriy in resolve endpoint #96.

- Allows using different kind of keys for signing in admin #98 / #53
- Allows using different kinds on keys in TA #99

- TA can do TLS if certificate and key are provided.
- `entity_type` as parement in resolve endpoint #106.

- `add_historical_key.py` to mark a key as expired/revoked for historical keys endpoint.
- Fixes #108, adds the historical keys endpoint

- The Admin API now has API call for historical_keys

## Changed

- Updates error handling in rust code #101.

## Fixed

- Fixes #46 removes old entity configuration code from TA.

- Fixes #104 `/trust_mark_status` accepts `POST` request according to the specification.

- Fixes #55 verifies that TA is allowed to be a authority for a subordinate.

<a id='changelog-0.1.3'></a>
# 0.1.3 — 2025-12-16

## Added

- #52 we now have additional_claims for TrustMark.

- Check for only our TrustMarks via keyvalue store.
- Run `reload_issued_tms` management command to load them at start, right now
  it is in `docker-entrypoing.sh` file.

## Fixed

- #51 Trustmarks now have hours in expiry.

- #50 removes trustmark from redis if not active.

- #80 list endpoint for TrustMark is now at `/trust_mark_list`.

- #49 add details in server entity test in api.

- #48 updates test to verify trustmark renewal details

<a id='changelog-0.1.2'></a>
# 0.1.2 — 2025-11-19

## Fixed

- Fixed #70, `/list` endpoint in TA now fetches data from redis.
