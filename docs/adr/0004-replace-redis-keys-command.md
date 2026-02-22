# ADR 0004: Replace Redis KEYS Command with Non-blocking Alternatives

## Status

Accepted

## Context

The Redis `KEYS` command scans the entire keyspace in a single blocking
operation (O(N) where N is the total number of keys in the database). While
convenient, it blocks the Redis event loop for the duration of the scan,
causing latency spikes for all other Redis clients.

Inmor used `KEYS` in two places:

1. **`/status` endpoint** (`src/lib.rs`): `KEYS inmor:tmtype:*` to enumerate
   trust mark types. This is user-facing and can be hit repeatedly.

2. **`run_collection_walk`** (`src/tree.rs`): Three `KEYS` calls to clean
   staging keys, delete live keys, and rename staging to live. These are
   CLI-triggered via `inmor-collection` and less critical, but still
   unnecessary.

## Decision

We replace all `KEYS` usage with two strategies:

### Index set for trust mark types

An `inmor:tmtypes` Redis set is maintained as a side-index. When a trust
mark is issued via the Admin portal, `SADD inmor:tmtypes <type_url>` is
called alongside the existing `SADD inmor:tmtype:<type_url> <entity>`. The
`/status` endpoint uses `SMEMBERS inmor:tmtypes` instead of
`KEYS inmor:tmtype:*`.

This is O(N) where N is the number of trust mark types (typically < 20),
stays inside the existing Redis pipeline (single round-trip), and is
idempotent (re-adding the same member is a no-op).

### Deterministic key enumeration for collection walk

The collection keys follow a fixed naming pattern based on
`KNOWN_ENTITY_TYPES`. A `known_collection_keys(prefix)` helper generates
the complete list of possible keys for a given prefix. `DEL` on
non-existent keys is a no-op, so no existence check is needed.

This eliminates all three `KEYS` calls in `run_collection_walk` and removes
the need to filter staging keys from live key results.

## Consequences

- The Redis `KEYS` command is no longer used anywhere in the codebase.
- The `/status` endpoint no longer risks blocking Redis under high load.
- The `inmor:tmtypes` set is append-only; trust mark types are never deleted
  in the current system, so no cleanup logic is needed.
- For fresh Redis instances without `inmor:tmtypes`, `SMEMBERS` returns an
  empty set, which degrades gracefully.
- The `known_collection_keys` helper must be updated if new collection key
  patterns are added, but this is preferable to scanning the keyspace.
