
<a id='changelog-0.3.0'></a>
# 0.3.0 — 2026-02-27

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
