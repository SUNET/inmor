//! Async tree walking module for federation entity discovery.
//!
//! Walks a federation tree starting from a trust anchor, discovering all
//! subordinate entities and storing their collection data in Redis.

use anyhow::Result;
use log::{debug, error, info, warn};
use redis::AsyncCommands;
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::{
    EntityCollectionResponse, UiInfo, get_entity_configruation_as_jwt, get_query, self_verify_jwt,
};

/// Prefix for staging keys used during tree walk.
/// Data is written here first, then atomically swapped to live keys.
const STAGING_PREFIX: &str = "inmor:collection:staging";

/// Known entity type keys we look for in metadata.
const KNOWN_ENTITY_TYPES: &[&str] = &[
    "openid_provider",
    "openid_relying_party",
    "federation_entity",
    "oauth_authorization_server",
    "oauth_client",
    "oauth_resource",
];

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
            Err(e) => {
                error!("Failed to verify authority hint JWT for {ahint_str}: {e}");
                continue;
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

/// Extract UI info from metadata for each entity type.
fn extract_ui_infos(metadata: &serde_json::Map<String, Value>) -> HashMap<String, UiInfo> {
    let mut ui_infos = HashMap::new();

    for &etype in KNOWN_ENTITY_TYPES {
        if let Some(type_meta) = metadata.get(etype).and_then(|v| v.as_object()) {
            let ui = UiInfo {
                display_name: type_meta
                    .get("organization_name")
                    .or_else(|| type_meta.get("client_name"))
                    .and_then(|v| v.as_str())
                    .map(String::from),
                description: None,
                logo_uri: type_meta
                    .get("logo_uri")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                policy_uri: type_meta
                    .get("policy_uri")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                information_uri: None,
            };
            ui_infos.insert(etype.to_string(), ui);
        }
    }

    ui_infos
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

/// Walks a single entity: fetches config, classifies, stores collection data,
/// then recurses into subordinates if the entity is a TA/IA.
async fn collection_tree_walking(
    entity_id: &str,
    conn: &mut redis::aio::ConnectionManager,
    visited: &mut HashSet<String>,
) {
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
        Err(e) => {
            error!("Failed to verify entity configuration for {entity_id}: {e}");
            return;
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

    // Extract UI info
    let ui_infos = extract_ui_infos(metadata);
    if !ui_infos.is_empty() {
        debug!(
            "Extracted UI info for {entity_id}: {}",
            ui_infos
                .iter()
                .map(|(k, v)| format!("{k}: {}", v.display_name.as_deref().unwrap_or("(no name)")))
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

    // Build collection response
    let response = EntityCollectionResponse {
        entity_id: entity_id.to_string(),
        entity_types: entity_types.clone(),
        ui_infos: if ui_infos.is_empty() {
            None
        } else {
            Some(ui_infos)
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

    // If TA/IA, discover subordinates via list endpoint and recurse
    if let Some(fed_entity) = metadata
        .get("federation_entity")
        .and_then(|v| v.as_object())
        && let Some(list_endpoint) = fed_entity
            .get("federation_list_endpoint")
            .and_then(|v| v.as_str())
    {
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
                            Box::pin(collection_tree_walking(sub_str, conn, visited)).await;
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

/// Runs a full collection walk starting from the given trust anchor.
///
/// Writes to staging Redis keys during the walk, then atomically swaps
/// them to live keys so `/collection` never sees partial data.
pub async fn run_collection_walk(
    trust_anchor: &str,
    conn: &mut redis::aio::ConnectionManager,
) -> Result<usize> {
    info!("Starting collection walk from {trust_anchor}");

    // Clean any leftover staging data
    debug!("Cleaning leftover staging keys");
    let staging_keys: Vec<String> = redis::cmd("KEYS")
        .arg(format!("{STAGING_PREFIX}:*"))
        .query_async(conn)
        .await
        .unwrap_or_default();
    if !staging_keys.is_empty() {
        debug!("Deleting {} leftover staging key(s)", staging_keys.len());
        let _: Result<(), _> = redis::cmd("DEL").arg(&staging_keys).query_async(conn).await;
    } else {
        debug!("No leftover staging keys found");
    }

    // Walk the tree
    debug!("Beginning recursive tree walk from {trust_anchor}");
    let mut visited = HashSet::new();
    collection_tree_walking(trust_anchor, conn, &mut visited).await;

    let entity_count = visited.len();
    info!("Walk complete: {entity_count} entities discovered");

    // Atomic swap: delete old live keys, rename staging → live
    debug!("Preparing atomic swap of staging → live keys");
    let mut pipe = redis::pipe();

    // Delete old live collection keys
    let live_keys: Vec<String> = redis::cmd("KEYS")
        .arg("inmor:collection:*")
        .query_async(conn)
        .await
        .unwrap_or_default();
    // Filter out staging keys from the delete list
    let live_keys: Vec<&String> = live_keys
        .iter()
        .filter(|k| !k.starts_with(STAGING_PREFIX))
        .collect();
    if !live_keys.is_empty() {
        debug!("Deleting {} old live key(s)", live_keys.len());
        pipe.cmd("DEL").arg(live_keys).ignore();
    }

    // Rename staging keys to live
    let staging_keys: Vec<String> = redis::cmd("KEYS")
        .arg(format!("{STAGING_PREFIX}:*"))
        .query_async(conn)
        .await
        .unwrap_or_default();

    debug!("Renaming {} staging key(s) to live", staging_keys.len());
    for staging_key in &staging_keys {
        let live_key = staging_key.replace("inmor:collection:staging:", "inmor:collection:");
        debug!("  {staging_key} → {live_key}");
        pipe.cmd("RENAME").arg(staging_key).arg(&live_key).ignore();
    }

    // Set last_updated timestamp
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
