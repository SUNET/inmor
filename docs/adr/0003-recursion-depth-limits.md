# ADR 0003: Recursion Depth Limits for Trust Chain Resolution and Collection Walking

## Status

Accepted

## Context

Both `resolve_entity_to_trustanchor()` and `collection_tree_walking()` use
`Box::pin` recursion to traverse federation trust chains and entity trees.
While cycle detection exists via a `visited` HashSet, a chain of many unique
entities each pointing to the next would cause unbounded recursion depth and
a proportional number of outbound HTTP requests. A malicious or misconfigured
federation could exploit this to cause resource exhaustion.

## Decision

We add a `depth: u8` parameter to both recursive functions with a maximum
limit enforced at function entry:

- **`resolve_entity_to_trustanchor`**: `MAX_RESOLVE_DEPTH = 10`. Trust chain
  resolution is triggered by user-facing `/resolve` requests. Practical
  federations rarely exceed 3-4 levels (leaf -> intermediate -> TA).

- **`collection_tree_walking`**: `MAX_COLLECTION_DEPTH = 20`. Collection
  walks are CLI-triggered (not user-request-triggered) and federation trees
  can be wider and deeper than a single trust chain, so a higher limit is
  appropriate.

Callers pass `0` as the initial depth. Each recursive call increments
`depth + 1`. When the limit is exceeded, `resolve_entity_to_trustanchor`
returns an error and `collection_tree_walking` logs an error and returns.

## Consequences

- Trust chain resolution is bounded to at most 10 levels of recursion and
  ~20 outbound HTTP requests per level, preventing resource exhaustion from
  deep or malicious federation chains.
- Collection tree walking is bounded to 20 levels, sufficient for any
  realistic federation topology while preventing runaway recursion.
- Legitimate federations are unaffected — real-world chains are 2-4 levels
  deep.
- If a future federation legitimately exceeds these limits, the constants
  can be increased.
