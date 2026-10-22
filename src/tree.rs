//! Async tree walking module for federation entity discovery.
//!
//! Walks a federation tree starting from a trust anchor, discovering all
//! subordinate entities and storing their collection data in Redis.

use anyhow::Result;
use josekit::jwk::JwkSet;
use log::{debug, error, info, warn};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, HashSet};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::{
    COLLECTION_INFO_CLAIMS, EntityCollectionResponse, EntityTypeInfo, KNOWN_ENTITY_TYPES,
    TrustMarkOwners, get_entity_configruation_as_jwt, get_jwks_from_payload_or_uri, get_query,
    get_unverified_payload_header, self_verify_jwt, split_claim_lang, validate_redis_key_input,
    verify_jwt_with_jwks, verify_trust_marks,
};

/// Prefix for staging keys used during tree walk.
/// Data is written here first, then atomically swapped to live keys.
const STAGING_PREFIX: &str = "inmor:collection:staging";

/// Federation context captured once from the walk-from Trust Anchor's Entity
/// Configuration and threaded through the recursion. Lets the walker verify
/// each entity's Trust Marks against the same Trust Anchor used to collect the
/// federation (spec sec 3.3.1-2.4.1).
struct CollectionWalkContext {
    /// Entity Identifier of the Trust Anchor the walk started from.
    trust_anchor: String,
    /// The Trust Anchor's federation signing keys.
    ta_keyset: JwkSet,
    /// `trust_mark_issuers` recognition map from the Trust Anchor's EC.
    trust_mark_issuers: Map<String, Value>,
    /// `trust_mark_owners` pinned by the Trust Anchor.
    trust_mark_owners: TrustMarkOwners,
    /// Counts failed writes to the staging indexes that must be complete to
    /// be correct: `by_trustmark:{type}` / `trustmark_types` (the
    /// `/collection?trust_mark_type=...` filter) and `intermediates` (the
    /// `/status` and Admin Intermediate counts). A nonzero count means an
    /// index would be silently incomplete, so `run_collection_walk` aborts
    /// the swap and surfaces the failure instead of publishing inconsistent
    /// data.
    index_errors: AtomicU32,
}

impl CollectionWalkContext {
    /// Records the result of a write to a must-be-complete staging index:
    /// a failure is logged with `what` (built only on failure) and counted
    /// on `index_errors` so the walk refuses to publish.
    fn record_index_write(&self, result: redis::RedisResult<()>, what: impl FnOnce() -> String) {
        if let Err(e) = result {
            error!("{}: {e}", what());
            self.index_errors.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// Fails when any index write was recorded as failed, so the caller
    /// stops before swapping staging into the live collection.
    fn ensure_indexes_complete(&self) -> Result<()> {
        let errors = self.index_errors.load(Ordering::Relaxed);
        if errors > 0 {
            return Err(anyhow::anyhow!(
                "{errors} collection index write(s) failed; refusing to swap staging into the live collection"
            ));
        }
        Ok(())
    }
}

/// Fetches authority subordinate statements and stores them in Redis.
async fn fetch_all_subordinate_statements(
    authority_hints: &Value,
    entity_id: &str,
    conn: &mut redis::aio::ConnectionManager,
) {
    let Some(ahints) = authority_hints.as_array() else {
        return;
    };
    for ahint in ahints {
        let Some(ahint_str) = ahint.as_str() else {
            continue;
        };
        debug!("Fetching authority hint: {ahint_str}");
        let jwt_net = match get_entity_configruation_as_jwt(ahint_str).await {
            Ok(res) => res,
            Err(e) => {
                error!("Failed to fetch authority hint {ahint_str}: {e}");
                continue;
            }
        };

        let (entity_payload, _) = match self_verify_jwt(&jwt_net) {
            Ok(data) => data,
            Err(_) => {
                // Self-verification failed — try fetching JWKS from jwks_uri
                let (unverified_payload, _) = match get_unverified_payload_header(&jwt_net) {
                    Ok(data) => data,
                    Err(e) => {
                        error!("Failed to parse authority hint JWT for {ahint_str}: {e}");
                        continue;
                    }
                };
                match get_jwks_from_payload_or_uri(&unverified_payload, conn).await {
                    Ok(keyset) => match verify_jwt_with_jwks(&jwt_net, Some(keyset)) {
                        Ok(data) => data,
                        Err(e) => {
                            error!(
                                "Failed to verify authority hint JWT for {ahint_str} with fetched JWKS: {e}"
                            );
                            continue;
                        }
                    },
                    Err(e) => {
                        error!("Failed to get JWKS for authority hint {ahint_str}: {e}");
                        continue;
                    }
                }
            }
        };

        let metadata = match entity_payload.claim("metadata") {
            Some(value) => match value.as_object() {
                Some(obj) => obj,
                None => {
                    error!("Metadata is not an object for authority: {ahint_str}");
                    continue;
                }
            },
            None => {
                error!("Missing metadata claim for authority: {ahint_str}");
                continue;
            }
        };

        let fed_entity = match metadata.get("federation_entity") {
            Some(value) => match value.as_object() {
                Some(obj) => obj,
                None => {
                    error!("federation_entity is not an object for: {ahint_str}");
                    continue;
                }
            },
            None => {
                error!("Missing federation_entity in metadata for: {ahint_str}");
                continue;
            }
        };

        let fetch_endpoint = fed_entity.get("federation_fetch_endpoint");
        if let Some(fetch_endpoint) = fetch_endpoint
            && let Some(fetch_url) = fetch_endpoint.as_str()
        {
            let url = format!("{fetch_url}?sub={entity_id}");
            debug!("Fetching subordinate statement from {url}");
            match get_query(&url).await {
                Ok(jwt_str) => {
                    let _: Result<(), _> =
                        redis::Cmd::hset("inmor:subordinate_query", &url, jwt_str.as_bytes())
                            .query_async(conn)
                            .await;
                }
                Err(e) => {
                    error!("Failed to fetch subordinate statement from {url}: {e}");
                }
            }
        }
    }
}

/// Extracts the Entity Type Info object for each known entity type
/// (Entity Collection spec sec 5.2): every informational claim in
/// `COLLECTION_INFO_CLAIMS`, including language-tagged variants, followed by
/// the `display_name` fallbacks. Types without any such claim are omitted.
fn extract_entity_infos(metadata: &Map<String, Value>) -> BTreeMap<String, EntityTypeInfo> {
    let mut entity_infos = BTreeMap::new();

    for &etype in KNOWN_ENTITY_TYPES {
        if let Some(type_meta) = metadata.get(etype).and_then(|v| v.as_object()) {
            let mut info: EntityTypeInfo = type_meta
                .iter()
                .filter(|(claim, value)| {
                    !value.is_null() && COLLECTION_INFO_CLAIMS.contains(&split_claim_lang(claim).0)
                })
                .map(|(claim, value)| (claim.clone(), value.clone()))
                .collect();
            apply_display_name_fallback(etype, type_meta, &mut info);
            if !info.is_empty() {
                entity_infos.insert(etype.to_string(), info);
            }
        }
    }

    entity_infos
}

/// Fills `display_name` (per language tag) when the metadata does not set
/// it (spec sec 5.2): `client_name` for openid_relying_party / oauth_client,
/// `resource_name` for oauth_resource, then `organization_name` as a last
/// resort for every type.
fn apply_display_name_fallback(
    etype: &str,
    type_meta: &Map<String, Value>,
    info: &mut EntityTypeInfo,
) {
    let mut sources = match etype {
        "openid_relying_party" | "oauth_client" => vec!["client_name"],
        "oauth_resource" => vec!["resource_name"],
        _ => Vec::new(),
    };
    sources.push("organization_name");

    // Sources are visited in priority order, so the first value found for a
    // language tag wins and an explicit display_name is never overwritten.
    // Language tags are case-insensitive (RFC 5646 sec 2.1.1), so the
    // existing-value check ignores tag case: `client_name#sv-se` must not add
    // a second Swedish name next to `display_name#sv-SE`.
    for source in sources {
        for (claim, value) in type_meta {
            let (base, tag) = split_claim_lang(claim);
            if base != source || !value.is_string() || has_display_name(info, tag) {
                continue;
            }
            let target = match tag {
                Some(tag) => format!("display_name#{tag}"),
                None => "display_name".to_string(),
            };
            info.insert(target, value.clone());
        }
    }
}

/// Whether `info` already holds a `display_name` for the language tag
/// `tag` (`None` = the untagged value), comparing tags case-insensitively.
fn has_display_name(info: &EntityTypeInfo, tag: Option<&str>) -> bool {
    info.keys().any(|claim| match split_claim_lang(claim) {
        ("display_name", None) => tag.is_none(),
        ("display_name", Some(existing)) => tag.is_some_and(|t| t.eq_ignore_ascii_case(existing)),
        _ => false,
    })
}

/// The entity's `federation_list_endpoint`, when it is a string. Used both to
/// classify Intermediates and to discover subordinates, so the two can never
/// disagree: a `null` or otherwise non-string value makes the entity a leaf.
fn federation_list_endpoint(metadata: &Map<String, Value>) -> Option<&str> {
    metadata
        .get("federation_entity")
        .and_then(|v| v.get("federation_list_endpoint"))
        .and_then(|v| v.as_str())
}

/// Detect entity types present in metadata.
fn detect_entity_types(metadata: &serde_json::Map<String, Value>) -> Vec<String> {
    let mut types = Vec::new();
    for &etype in KNOWN_ENTITY_TYPES {
        if metadata.contains_key(etype) {
            types.push(etype.to_string());
        }
    }
    // Every entity in a federation is implicitly a federation_entity
    if !types.contains(&"federation_entity".to_string()) {
        types.push("federation_entity".to_string());
    }
    types
}

/// Maximum recursion depth for collection tree walking.
const MAX_COLLECTION_DEPTH: u8 = 20;

/// Walks a single entity: fetches config, classifies, stores collection data,
/// then recurses into subordinates if the entity is a TA/IA.
async fn collection_tree_walking(
    entity_id: &str,
    conn: &mut redis::aio::ConnectionManager,
    visited: &mut HashSet<String>,
    depth: u8,
    ctx: &CollectionWalkContext,
) {
    if depth > MAX_COLLECTION_DEPTH {
        error!(
            "Collection tree walking exceeded maximum depth of {} at {entity_id}",
            MAX_COLLECTION_DEPTH
        );
        return;
    }
    if visited.contains(entity_id) {
        debug!("Already visited {entity_id}, skipping");
        return;
    }
    visited.insert(entity_id.to_string());
    debug!("Processing entity #{}: {entity_id}", visited.len());

    // Fetch entity configuration
    debug!("Fetching entity configuration from {entity_id}/.well-known/openid-federation");
    let jwt_net = match get_entity_configruation_as_jwt(entity_id).await {
        Ok(res) => {
            debug!(
                "Fetched entity configuration for {entity_id} ({} bytes)",
                res.len()
            );
            res
        }
        Err(e) => {
            error!("Failed to fetch entity configuration for {entity_id}: {e}");
            return;
        }
    };

    // Verify
    debug!("Verifying entity configuration JWT for {entity_id}");
    let (payload, _) = match self_verify_jwt(&jwt_net) {
        Ok(data) => {
            debug!("JWT verification successful for {entity_id}");
            data
        }
        Err(_) => {
            // Self-verification failed — try fetching JWKS from jwks_uri
            debug!("Self-verification failed for {entity_id}, trying jwks_uri fallback");
            let (unverified_payload, _) = match get_unverified_payload_header(&jwt_net) {
                Ok(data) => data,
                Err(e) => {
                    error!("Failed to parse entity configuration JWT for {entity_id}: {e}");
                    return;
                }
            };
            match get_jwks_from_payload_or_uri(&unverified_payload, conn).await {
                Ok(keyset) => match verify_jwt_with_jwks(&jwt_net, Some(keyset)) {
                    Ok(data) => {
                        debug!("JWT verification successful for {entity_id} via jwks_uri");
                        data
                    }
                    Err(e) => {
                        error!(
                            "Failed to verify entity configuration for {entity_id} with fetched JWKS: {e}"
                        );
                        return;
                    }
                },
                Err(e) => {
                    error!("Failed to get JWKS for entity {entity_id}: {e}");
                    return;
                }
            }
        }
    };

    // Store entity JWT
    debug!("Storing entity JWT in Redis for {entity_id}");
    let _: Result<(), _> = redis::Cmd::hset("inmor:entities", entity_id, jwt_net.as_bytes())
        .query_async(conn)
        .await;

    // Fetch subordinate statements from authorities
    if let Some(authority_hints) = payload.claim("authority_hints") {
        let hint_count = authority_hints.as_array().map(|a| a.len()).unwrap_or(0);
        debug!("Entity {entity_id} has {hint_count} authority hint(s)");
        fetch_all_subordinate_statements(authority_hints, entity_id, conn).await;
    } else {
        debug!("Entity {entity_id} has no authority hints (likely a trust anchor)");
    }

    // Extract metadata
    let metadata = match payload.claim("metadata") {
        Some(value) => match value.as_object() {
            Some(obj) => obj,
            None => {
                error!("Metadata is not an object for {entity_id}");
                return;
            }
        },
        None => {
            error!("Missing metadata claim for {entity_id}");
            return;
        }
    };

    // Classify entity types
    let entity_types = detect_entity_types(metadata);
    info!(
        "Discovered {entity_id} with types: [{}]",
        entity_types.join(", ")
    );

    // Extract Entity Type Info
    let entity_infos = extract_entity_infos(metadata);
    if !entity_infos.is_empty() {
        debug!(
            "Extracted entity info for {entity_id}: {}",
            entity_infos
                .iter()
                .map(|(k, v)| format!(
                    "{k}: {}",
                    v.get("display_name")
                        .and_then(|n| n.as_str())
                        .unwrap_or("(no name)")
                ))
                .collect::<Vec<_>>()
                .join(", ")
        );
    }

    // Extract trust marks
    let trust_marks = payload
        .claim("trust_marks")
        .and_then(|v| v.as_array())
        .cloned();
    if let Some(ref tms) = trust_marks {
        debug!("Entity {entity_id} has {} trust mark(s)", tms.len());
    }

    // Verify the entity's Trust Marks against the walk-from Trust Anchor so the
    // trust_mark_type collection filter indexes only marks that actually pass
    // verification (spec sec 3.3.1-2.4.1). The response `trust_marks` field
    // keeps the raw array -- per Entity Collection spec sec 6.1 the returned
    // marks are informational and MAY be unverified.
    let verified_marks = verify_trust_marks(
        &payload,
        &ctx.trust_anchor,
        &ctx.ta_keyset,
        &ctx.trust_mark_issuers,
        &ctx.trust_mark_owners,
        conn,
    )
    .await;
    // The trust mark type strings are federation-provided and get used
    // verbatim in Redis key names (`...:by_trustmark:{tm_type}`). Drop any
    // value with control characters or an abusive length before indexing it.
    // Collect into a set so duplicate trust mark types on one entity only
    // trigger one Redis SADD (and at most one index-write error count bump).
    let verified_tm_types: HashSet<String> = verified_marks
        .iter()
        .filter_map(|m| {
            m.get("trust_mark_type")
                .and_then(|v| v.as_str())
                .map(String::from)
        })
        .filter(|tm_type| match validate_redis_key_input(tm_type) {
            Ok(()) => true,
            Err(e) => {
                warn!("Skipping unsafe trust mark type for {entity_id}: {e}");
                false
            }
        })
        .collect();
    if !verified_tm_types.is_empty() {
        debug!(
            "Entity {entity_id} has {} verified trust mark type(s)",
            verified_tm_types.len()
        );
    }

    // Build collection response
    let response = EntityCollectionResponse {
        entity_id: entity_id.to_string(),
        entity_types: entity_types.clone(),
        entity_infos: if entity_infos.is_empty() {
            None
        } else {
            Some(entity_infos)
        },
        trust_marks,
    };

    // Store in staging Redis keys
    debug!("Storing collection data in staging for {entity_id}");
    let response_json = serde_json::to_string(&response).unwrap_or_default();
    let _: Result<(), _> = redis::Cmd::hset(
        format!("{STAGING_PREFIX}:entities"),
        entity_id,
        &response_json,
    )
    .query_async(conn)
    .await;

    for etype in &entity_types {
        let _: Result<(), _> =
            redis::Cmd::sadd(format!("{STAGING_PREFIX}:by_type:{etype}"), entity_id)
                .query_async(conn)
                .await;
    }

    // ZADD with score 0 for lexicographic ordering
    let _: Result<(), _> =
        redis::Cmd::zadd(format!("{STAGING_PREFIX}:all_sorted"), entity_id, 0i64)
            .query_async(conn)
            .await;

    // Index verified trust mark types so the trust_mark_type filter can
    // resolve entities by type. `trustmark_types` is a registry of every
    // indexed type, needed because by_trustmark keys are dynamic URLs.
    // Errors here are critical: a missing index entry silently truncates
    // `/collection?trust_mark_type=...` responses, so record any failure on
    // the shared counter so `run_collection_walk` can abort the swap.
    for tm_type in &verified_tm_types {
        let result = redis::Cmd::sadd(
            format!("{STAGING_PREFIX}:by_trustmark:{tm_type}"),
            entity_id,
        )
        .query_async::<()>(conn)
        .await;
        ctx.record_index_write(result, || {
            format!("Failed to index trust mark type {tm_type} for {entity_id}")
        });
        let result = redis::Cmd::sadd(format!("{STAGING_PREFIX}:trustmark_types"), tm_type)
            .query_async::<()>(conn)
            .await;
        ctx.record_index_write(result, || {
            format!("Failed to record trust mark type {tm_type} in registry")
        });
    }

    // Also populate the existing inmor:op/rp/taia sets for backward compat
    if metadata.contains_key("openid_relying_party") {
        let _: Result<(), _> = redis::Cmd::sadd("inmor:rp", entity_id)
            .query_async(conn)
            .await;
    } else if metadata.contains_key("openid_provider") {
        let _: Result<(), _> = redis::Cmd::sadd("inmor:op", entity_id)
            .query_async(conn)
            .await;
    } else {
        let _: Result<(), _> = redis::Cmd::sadd("inmor:taia", entity_id)
            .query_async(conn)
            .await;
    }

    // An entity below the Trust Anchor that lists subordinates is an
    // Intermediate; index it for the `/status` intermediates count. A failed
    // write would publish an undercount, so it blocks the swap like the
    // trust mark index.
    let list_endpoint = federation_list_endpoint(metadata);
    if list_endpoint.is_some() && entity_id != ctx.trust_anchor {
        let result = redis::Cmd::sadd(format!("{STAGING_PREFIX}:intermediates"), entity_id)
            .query_async::<()>(conn)
            .await;
        ctx.record_index_write(result, || {
            format!("Failed to index Intermediate {entity_id}")
        });
    }

    // If TA/IA, discover subordinates via list endpoint and recurse
    if let Some(list_endpoint) = list_endpoint {
        debug!("Entity {entity_id} has list endpoint: {list_endpoint}");
        debug!("Fetching subordinate list from {list_endpoint}");
        match get_query(list_endpoint).await {
            Ok(resp) => {
                if let Ok(subs) = serde_json::from_str::<Value>(&resp)
                    && let Some(sub_array) = subs.as_array()
                {
                    debug!(
                        "List endpoint returned {} subordinate(s) for {entity_id}",
                        sub_array.len()
                    );
                    for sub in sub_array {
                        if let Some(sub_str) = sub.as_str() {
                            if visited.contains(sub_str) {
                                debug!("Skipping {sub_str} (already visited)");
                                continue;
                            }
                            info!("Found subordinate: {sub_str}");
                            Box::pin(collection_tree_walking(
                                sub_str,
                                conn,
                                visited,
                                depth + 1,
                                ctx,
                            ))
                            .await;
                        }
                    }
                }
            }
            Err(e) => {
                error!("Failed to fetch list from {list_endpoint}: {e}");
            }
        }
    } else {
        debug!("Entity {entity_id} is a leaf (no list endpoint)");
    }
}

/// Returns the list of known collection Redis keys for a given prefix.
/// This avoids using the KEYS command which blocks the Redis event loop.
///
/// `trustmark_types` enumerates the dynamic `by_trustmark:{type}` keys; pass
/// the trust mark types recorded in the matching `trustmark_types` registry
/// set for the prefix.
fn known_collection_keys(prefix: &str, trustmark_types: &[String]) -> Vec<String> {
    let mut keys = vec![
        format!("{prefix}:entities"),
        format!("{prefix}:all_sorted"),
        format!("{prefix}:trust_anchor"),
        format!("{prefix}:trustmark_types"),
        format!("{prefix}:intermediates"),
    ];
    for etype in KNOWN_ENTITY_TYPES {
        keys.push(format!("{prefix}:by_type:{etype}"));
    }
    for tm_type in trustmark_types {
        keys.push(format!("{prefix}:by_trustmark:{tm_type}"));
    }
    keys
}

/// Fetches and verifies the walk-from Trust Anchor's Entity Configuration and
/// extracts the recognition context used for Trust Mark verification.
async fn build_walk_context(
    trust_anchor: &str,
    conn: &mut redis::aio::ConnectionManager,
) -> Result<CollectionWalkContext> {
    let jwt = get_entity_configruation_as_jwt(trust_anchor).await?;
    let (payload, _) = match self_verify_jwt(&jwt) {
        Ok(data) => data,
        Err(_) => {
            // Self-verification failed -- try the jwks_uri fallback.
            let (unverified, _) = get_unverified_payload_header(&jwt)?;
            let keyset = get_jwks_from_payload_or_uri(&unverified, conn).await?;
            verify_jwt_with_jwks(&jwt, Some(keyset))?
        }
    };
    // Resolve the Trust Anchor's federation keys allowing the jwks_uri /
    // signed_jwks_uri fallback, so collection also works for a Trust Anchor
    // that publishes its keys by reference rather than inline.
    let ta_keyset = get_jwks_from_payload_or_uri(&payload, conn).await?;
    // Recognition maps. A malformed `trust_mark_owners` claim fails closed:
    // both maps are emptied so no trust mark is recognised. Keeping
    // `trust_mark_issuers` while dropping owners would silently skip
    // delegation enforcement for owned types that also appear in the issuers
    // map (the fail-open case documented on `TrustMarkOwners::from_ta_payload`).
    let (trust_mark_issuers, trust_mark_owners) = match TrustMarkOwners::from_ta_payload(&payload) {
        Ok(owners) => {
            let issuers = payload
                .claim("trust_mark_issuers")
                .and_then(|v| v.as_object())
                .cloned()
                .unwrap_or_default();
            (issuers, owners)
        }
        Err(e) => {
            error!(
                "Trust anchor {trust_anchor} has a malformed trust_mark_owners claim ({e}); \
                 collection will recognise no trust marks at all"
            );
            (Map::new(), TrustMarkOwners::default())
        }
    };
    Ok(CollectionWalkContext {
        trust_anchor: trust_anchor.to_string(),
        ta_keyset,
        trust_mark_issuers,
        trust_mark_owners,
        index_errors: AtomicU32::new(0),
    })
}

/// Runs a full collection walk starting from the given trust anchor.
///
/// Writes to staging Redis keys during the walk, then atomically swaps
/// them to live keys so `/collection` never sees partial data.
pub async fn run_collection_walk(
    trust_anchor: &str,
    conn: &mut redis::aio::ConnectionManager,
) -> Result<usize> {
    info!("Starting collection walk from {trust_anchor}");

    // Build the walk context (recognition maps + TA keys) up front. A failure
    // here aborts before any live data is touched.
    let ctx = build_walk_context(trust_anchor, conn).await?;

    // Clean any leftover staging data, including dynamic by_trustmark keys
    // left behind by a previous interrupted run.
    let stale_types: Vec<String> =
        redis::Cmd::smembers(format!("{STAGING_PREFIX}:trustmark_types"))
            .query_async(conn)
            .await
            .unwrap_or_default();
    let staging_keys = known_collection_keys(STAGING_PREFIX, &stale_types);
    debug!(
        "Cleaning {} possible leftover staging key(s)",
        staging_keys.len()
    );
    let _: Result<(), _> = redis::cmd("DEL").arg(&staging_keys).query_async(conn).await;

    // Record the Trust Anchor this collection was built from so /collection
    // can validate the request `trust_anchor` parameter against it. This
    // write is required: without it the live collection would reject every
    // request that supplies `trust_anchor=...` with `invalid_request`.
    redis::Cmd::set(format!("{STAGING_PREFIX}:trust_anchor"), trust_anchor)
        .query_async::<()>(conn)
        .await
        .map_err(|e| anyhow::anyhow!("failed to record staging trust_anchor: {e}"))?;

    // Walk the tree
    debug!("Beginning recursive tree walk from {trust_anchor}");
    let mut visited = HashSet::new();
    collection_tree_walking(trust_anchor, conn, &mut visited, 0, &ctx).await;

    let entity_count = visited.len();
    info!("Walk complete: {entity_count} entities discovered");

    // Abort before the atomic swap if any trust mark or Intermediate index
    // write failed -- publishing the collection would yield silently
    // incomplete `trust_mark_type` filter results or Intermediate counts.
    ctx.ensure_indexes_complete()?;

    // Atomic swap: delete old live keys, rename staging -> live.
    debug!("Preparing atomic swap of staging -> live keys");

    // Trust mark types discovered in this walk drive the staging by_trustmark
    // key set; the previous live set drives the old-key cleanup.
    let new_types: Vec<String> = redis::Cmd::smembers(format!("{STAGING_PREFIX}:trustmark_types"))
        .query_async(conn)
        .await
        .unwrap_or_default();
    let old_types: Vec<String> = redis::Cmd::smembers("inmor:collection:trustmark_types")
        .query_async(conn)
        .await
        .unwrap_or_default();

    // RENAME errors on a missing source key, so swap only the staging keys
    // actually written during this walk.
    let candidate_staging = known_collection_keys(STAGING_PREFIX, &new_types);
    let mut exists_pipe = redis::pipe();
    for key in &candidate_staging {
        exists_pipe.cmd("EXISTS").arg(key);
    }
    let exists_flags: Vec<bool> = exists_pipe.query_async(conn).await?;
    let existing_staging: Vec<&String> = candidate_staging
        .iter()
        .zip(exists_flags)
        .filter_map(|(key, exists)| if exists { Some(key) } else { None })
        .collect();

    // MULTI/EXEC so a concurrent /collection request never observes a
    // half-swapped collection.
    let mut pipe = redis::pipe();
    pipe.atomic();

    // Delete old live collection keys.
    let mut live_keys = known_collection_keys("inmor:collection", &old_types);
    live_keys.push("inmor:collection:last_updated".to_string());
    debug!("Deleting {} old live key(s)", live_keys.len());
    pipe.cmd("DEL").arg(&live_keys).ignore();

    // Rename staging keys to live.
    debug!("Renaming {} staging key(s) to live", existing_staging.len());
    for staging_key in &existing_staging {
        let live_key = staging_key.replace("inmor:collection:staging:", "inmor:collection:");
        debug!("  {staging_key} -> {live_key}");
        pipe.cmd("RENAME").arg(*staging_key).arg(&live_key).ignore();
    }

    // Set last_updated timestamp.
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    pipe.cmd("SET")
        .arg("inmor:collection:last_updated")
        .arg(now)
        .ignore();

    debug!("Executing atomic swap pipeline");
    pipe.query_async::<()>(conn).await?;

    info!("Collection data swapped to live keys (last_updated={now})");
    Ok(entity_count)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// Unwraps a JSON object literal into an EC `metadata` map.
    fn metadata(value: Value) -> Map<String, Value> {
        value.as_object().cloned().unwrap()
    }

    /// Only allowlisted informational claims are collected.
    #[test]
    fn test_extract_entity_infos_copies_allowlisted_claims() {
        let md = metadata(json!({
            "openid_provider": {
                "display_name": "Example OP",
                "display_name#sv": "Exempel OP",
                "description": "An OP",
                "keywords": ["university"],
                "logo_uri": "https://op.example.com/logo.png",
                "information_uri": "https://op.example.com/info",
                "issuer": "https://op.example.com",
                "jwks": {"keys": []},
                "policy_uri": null
            }
        }));
        let infos = extract_entity_infos(&md);
        let op = &infos["openid_provider"];
        assert_eq!(op["display_name"], "Example OP");
        assert_eq!(op["display_name#sv"], "Exempel OP");
        assert_eq!(op["keywords"], json!(["university"]));
        assert_eq!(op["information_uri"], "https://op.example.com/info");
        // Non-informational metadata and null values are never copied.
        assert!(!op.contains_key("issuer"));
        assert!(!op.contains_key("jwks"));
        assert!(!op.contains_key("policy_uri"));
    }

    /// `display_name` falls back per spec sec 5.2, then to `organization_name`.
    #[test]
    fn test_extract_entity_infos_display_name_fallbacks() {
        let md = metadata(json!({
            "openid_relying_party": {
                "client_name": "Example RP",
                "client_name#sv": "Exempel RP",
                "organization_name": "Example Org"
            },
            "oauth_resource": {"resource_name": "Example API"},
            "federation_entity": {"organization_name": "Example Org"},
            "openid_provider": {
                "display_name": "Explicit",
                "organization_name": "Example Org"
            }
        }));
        let infos = extract_entity_infos(&md);
        // client_name wins over organization_name, per language tag.
        assert_eq!(infos["openid_relying_party"]["display_name"], "Example RP");
        assert_eq!(
            infos["openid_relying_party"]["display_name#sv"],
            "Exempel RP"
        );
        assert_eq!(infos["oauth_resource"]["display_name"], "Example API");
        // organization_name is the last resort and is also kept as its own claim.
        assert_eq!(infos["federation_entity"]["display_name"], "Example Org");
        assert_eq!(
            infos["federation_entity"]["organization_name"],
            "Example Org"
        );
        // An explicit display_name is never overwritten.
        assert_eq!(infos["openid_provider"]["display_name"], "Explicit");
    }

    /// Fallback display names never duplicate a language that already has
    /// one under different tag casing (regression: `display_name#sv-SE` and
    /// `client_name#sv-se` produced two Swedish names).
    #[test]
    fn test_display_name_fallback_ignores_tag_case() {
        let md = metadata(json!({
            "openid_relying_party": {
                "display_name#sv-SE": "Explicit SV",
                "client_name#sv-se": "Client SV",
                "client_name#FI": "Client FI",
                "organization_name#fi": "Org FI",
                "organization_name#de": "Org DE"
            }
        }));
        let rp = &extract_entity_infos(&md)["openid_relying_party"];
        let display_names: Vec<&String> = rp
            .keys()
            .filter(|k| split_claim_lang(k).0 == "display_name")
            .collect();
        // One display name per language: the explicit sv-SE value wins over
        // client_name#sv-se, client_name#FI wins over organization_name#fi,
        // and organization_name still fills a language nobody else covers.
        assert_eq!(display_names.len(), 3, "{display_names:?}");
        assert_eq!(rp["display_name#sv-SE"], "Explicit SV");
        assert_eq!(rp["display_name#FI"], "Client FI");
        assert_eq!(rp["display_name#de"], "Org DE");
    }

    /// A walk context with empty recognition maps, for index bookkeeping tests.
    fn test_context() -> CollectionWalkContext {
        CollectionWalkContext {
            trust_anchor: "https://ta.example.com".to_string(),
            ta_keyset: JwkSet::new(),
            trust_mark_issuers: Map::new(),
            trust_mark_owners: TrustMarkOwners::default(),
            index_errors: AtomicU32::new(0),
        }
    }

    /// Successful index writes leave the walk publishable.
    #[test]
    fn test_index_writes_ok_allow_publication() {
        let ctx = test_context();
        ctx.record_index_write(Ok(()), || unreachable!("only built on failure"));
        assert!(ctx.ensure_indexes_complete().is_ok());
    }

    /// Any failed index write (trust mark or Intermediate) blocks publication
    /// (regression: a failed Intermediate SADD was ignored and the walk still
    /// swapped, publishing an undercount).
    #[test]
    fn test_failed_index_write_blocks_publication() {
        let ctx = test_context();
        let failure = || {
            Err(redis::RedisError::from((
                redis::ErrorKind::IoError,
                "connection lost",
            )))
        };
        ctx.record_index_write(failure(), || "Failed to index Intermediate".to_string());
        ctx.record_index_write(failure(), || "Failed to index trust mark type".to_string());
        let err = ctx.ensure_indexes_complete().unwrap_err().to_string();
        assert!(err.contains("2 collection index write(s) failed"), "{err}");
    }

    /// Only a string `federation_list_endpoint` makes an entity list
    /// subordinates (regression: `null` was counted as an Intermediate while
    /// discovery treated the entity as a leaf).
    #[test]
    fn test_federation_list_endpoint_requires_string() {
        let with = |value: Value| {
            metadata(json!({"federation_entity": {"federation_list_endpoint": value}}))
        };
        assert_eq!(
            federation_list_endpoint(&with(json!("https://ia.example.com/list"))),
            Some("https://ia.example.com/list")
        );
        assert_eq!(federation_list_endpoint(&with(Value::Null)), None);
        assert_eq!(federation_list_endpoint(&with(json!(42))), None);
        assert_eq!(federation_list_endpoint(&with(json!(["x"]))), None);
        assert_eq!(
            federation_list_endpoint(&metadata(json!({"federation_entity": {}}))),
            None
        );
        assert_eq!(
            federation_list_endpoint(&metadata(json!({"openid_provider": {}}))),
            None
        );
    }

    /// Types without informational claims, and unknown types, are omitted.
    #[test]
    fn test_extract_entity_infos_skips_types_without_info() {
        let md = metadata(json!({
            "openid_provider": {"issuer": "https://op.example.com"},
            "unknown_type": {"display_name": "Ignored"}
        }));
        assert!(extract_entity_infos(&md).is_empty());
    }
}
