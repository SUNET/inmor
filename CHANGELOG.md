
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
