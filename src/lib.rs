pub mod tree;
use anyhow::{Result, anyhow, bail};

use lazy_static::lazy_static;
use log::{debug, warn};
use sha2::{Digest, Sha256};
use std::fmt::Display;
use std::net::IpAddr;
use std::sync::atomic::AtomicBool;

use actix_web::{HttpRequest, HttpResponse, Responder, error, get, post, web};
use actix_web_lab::extract::Query;
use base64::Engine;
use josekit::{
    JoseError,
    jwk::{Jwk, JwkSet},
    jws::{ES256, ES384, ES512, EdDSA, JwsHeader, JwsSigner, JwsVerifier, PS256, RS256},
    jwt::{self, JwtPayload, JwtPayloadValidator},
};
use oidfed_metadata_policy::*;
use serde::Deserialize;
use serde::Serialize;
use serde_json::{Map, Value, json};
use std::collections::{HashMap, HashSet};
use std::error::Error as StdError;
use std::ops::Deref;
use std::sync::Mutex;
use std::time::{Duration, SystemTime};
use std::{env, fs};

lazy_static! {
    static ref PUBLIC_KEYS: Vec<Vec<u8>> = {
        let mut keys = Vec::new();
        if let Ok(entries) = fs::read_dir("./publickeys") {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_file()
                    && let Some(ext) = path.extension()
                    && (ext == "json" || ext == "pub")
                    && let Ok(data) = fs::read(&path)
                {
                    keys.push(data);
                }
            }
        }
        keys
    };
    static ref PRIVATE_KEY: Vec<u8> = std::fs::read("./private.json").expect(
        "Failed to read ./private.json; create it via `just dev` or place the JWK in the working directory"
    );
    /// Shared HTTP client for all outbound federation requests.
    /// Configured with timeouts and connection limits.
    static ref HTTP_CLIENT: reqwest::Client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .pool_max_idle_per_host(10)
        .redirect(reqwest::redirect::Policy::limited(5))
        .build()
        .expect("Failed to build HTTP client");
}
pub const WELL_KNOWN: &str = ".well-known/openid-federation";

/// Claim names this codebase parses or otherwise acts on.
///
/// Per OpenID Federation §3.1.1, an issuer can set `crit` on a statement to
/// require recipients to reject it if they don't understand a listed claim
/// name. `verify_jwt_with_jwks` enforces that rule by checking every entry of
/// `crit` against this list. Every new claim that gets a `.claim("…")` parse
/// site MUST be appended here, otherwise an issuer that marks the new claim
/// critical will see its (correctly-formed) statements rejected.
///
/// Single-tenant note: under the planned multi-tenant work
/// (`multitenant_plan.md`), producer-side per-tenant `crit` policy is layered
/// on top of this consumer-side allowlist; the allowlist itself is a property
/// of inmor's parser capability and stays global.
pub const KNOWN_CLAIMS: &[&str] = &[
    "iss",
    "sub",
    "iat",
    "exp",
    "nbf",
    "jwks",
    "jwks_uri",
    "signed_jwks_uri",
    "metadata",
    "metadata_policy",
    "metadata_policy_crit",
    "trust_marks",
    "trust_mark_issuers",
    "trust_mark_owners",
    "authority_hints",
    "constraints",
    "trust_mark_type",
    "trust_mark",
    "status",
    "logo_uri",
    "ref",
    "delegation",
    "crit",
];

/// Force-load the TA's signing key so a missing or unreadable `./private.json`
/// fails at startup rather than on the first request that needs to sign.
pub fn ensure_signing_key_loaded() {
    let _ = PRIVATE_KEY.len();
}

/// Maximum response body size for outbound federation requests (2 MB).
const MAX_RESPONSE_BYTES: usize = 2_097_152;

/// Maximum number of retries inside `get_query` before classifying the
/// failure as a final transient error.
const FETCH_MAX_RETRIES: u32 = 2;

/// Initial backoff between retries inside `get_query`.
const FETCH_BACKOFF_INITIAL_MS: u64 = 250;

/// Cap on the per-retry backoff inside `get_query`.
const FETCH_BACKOFF_CAP_MS: u64 = 1_000;

/// Wall-clock budget for the chain-fetch phase of `/resolve`. Mirrors
/// `TRUST_MARK_VERIFICATION_BUDGET_SECS` so the worst-case worker time is
/// bounded even when an upstream is intermittently slow. Exceeding it is
/// treated as transient at the resolve boundary.
const CHAIN_FETCH_BUDGET_SECS: u64 = 15;

/// Default `Retry-After` value (seconds) suggested to clients when inmor
/// classifies a fetch failure as transient and the upstream did not provide
/// its own hint.
const DEFAULT_RETRY_AFTER_SECS: u64 = 10;

/// Classified outcome of an outbound federation HTTP fetch.
///
/// Spec §10.5 expects a resolver to distinguish transient failures (5xx,
/// 429, connection error, timeout, DNS failure) from permanent ones (4xx
/// other than 429, SSRF-gate denial, malformed response). inmor retries
/// transient failures inside `get_query` and, if retries are exhausted,
/// builds a `FetchError::transient(...)`. The chain walker propagates
/// transients up to `/resolve`, which emits HTTP 503 with `Retry-After`.
/// Permanent errors keep the existing HTTP 400 `invalid_trust_chain`
/// behaviour.
#[derive(Debug)]
pub struct FetchError {
    pub transient: bool,
    pub retry_after_seconds: Option<u64>,
    pub message: String,
}

impl FetchError {
    pub fn transient(retry_after: Option<u64>, msg: impl Into<String>) -> Self {
        Self {
            transient: true,
            retry_after_seconds: retry_after,
            message: msg.into(),
        }
    }

    pub fn permanent(msg: impl Into<String>) -> Self {
        Self {
            transient: false,
            retry_after_seconds: None,
            message: msg.into(),
        }
    }
}

impl Display for FetchError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if self.transient {
            write!(f, "transient fetch error: {}", self.message)
        } else {
            write!(f, "permanent fetch error: {}", self.message)
        }
    }
}

impl StdError for FetchError {}

/// When true, allows HTTP scheme and private/loopback IPs in outbound federation requests.
/// Only enable for development. Set from `allow_http` in `taconfig.toml`.
pub static ALLOW_HTTP: AtomicBool = AtomicBool::new(false);

// This struct represents state
pub struct AppState {
    pub entity_id: String,
    pub public_keyset: JwkSet,
}

// To represent the entities in the federation.
// FIXME: add all different data as proper part of the structure.
#[derive(Debug, Clone, Deserialize)]
pub struct EntityDetails {
    pub entity_id: String,
    pub entity_types: HashSet<String>,
    pub has_trustmark: bool,
    pub trustmarks: HashSet<String>,
}

impl EntityDetails {
    pub fn new(entity_id: &str, entity_types: HashSet<String>, trustmarks: Option<&Value>) -> Self {
        let mut has_trustmark = false;
        let mut tms: HashSet<String> = HashSet::new();

        // https://openid.net/specs/openid-federation-1_0.html#section-7.4
        // Trustmarks is an arrary of objects, with two keys
        // `trust_mark` and `trust_mark_type`.
        if let Some(trustms) = trustmarks {
            // Means we have some trustmarks hopefully
            if let Some(trustmark_array) = trustms.as_array() {
                for one_tm in trustmark_array.iter() {
                    if let Some(one_tm_obj) = one_tm.as_object()
                        && let Some(tm_type) = one_tm_obj.get("trust_mark_type")
                        && let Some(tm_str) = tm_type.as_str()
                    {
                        tms.insert(tm_str.to_owned());
                    }
                }
            }
        }

        // If we have any trustmarks
        if !tms.is_empty() {
            has_trustmark = true;
        }
        EntityDetails {
            entity_id: entity_id.to_string(),
            entity_types,
            has_trustmark,
            trustmarks: tms,
        }
    }
}

// This will be shared about threads via AppData
#[derive(Debug, Deserialize)]
pub struct Federation {
    pub entities: Mutex<HashMap<String, EntityDetails>>,
}

// SECTION FOR WEB QUERY PARAMETERS

/// https://openid.net/specs/openid-federation-1_0.html#section-8.3.1
#[derive(Debug, Deserialize)]
pub struct ResolveParams {
    sub: String,
    #[serde(rename = "trust_anchor")]
    trust_anchors: Vec<String>,
    /// Optional entity_type parameter to filter metadata keys in the response.
    /// If provided, only metadata keys matching the given entity types are returned.
    /// If not provided or if no matching types found, all metadata is returned.
    entity_type: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct TrustMarkParams {
    trust_mark_type: String,
    sub: String,
}

#[derive(Debug, Deserialize)]
pub struct TrustMarkListParams {
    trust_mark_type: String,
    sub: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct TrustMarkStatusParams {
    trust_mark: String,
}

/// https://openid.net/specs/openid-federation-1_0.html#section-8.2.1
/// All parameters are optional here according to the SPEC.
#[derive(Debug, Serialize, Deserialize)]
pub struct SubListingParams {
    entity_type: Option<Vec<String>>,
    trust_marked: Option<bool>,
    trust_mark_type: Option<String>,
    intermediate: Option<bool>,
}

// QUERY PARAMETERS ENDS

// Response type(s)

/// For https://zachmann.github.io/openid-federation-entity-collection/main.html#section-2.3.2.2

#[derive(Debug, Deserialize, Serialize)]
pub struct UiInfo {
    pub display_name: Option<String>,
    pub description: Option<String>,
    pub logo_uri: Option<String>,
    pub policy_uri: Option<String>,
    pub information_uri: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct EntityCollectionResponse {
    pub entity_id: String,
    pub entity_types: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ui_infos: Option<HashMap<String, UiInfo>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trust_marks: Option<Vec<Value>>,
}

impl EntityCollectionResponse {
    pub fn new(entity_id: String, entity_types: Vec<String>) -> Self {
        EntityCollectionResponse {
            entity_id,
            entity_types,
            ui_infos: None,
            trust_marks: None,
        }
    }
}

/// To store each JWT and verified payload from it
/// This will be used to return the final result
#[derive(Debug)]
pub struct VerifiedJWT {
    jwt: String,
    payload: JwtPayload,
    substatement: bool,
    taresult: bool,
}

impl VerifiedJWT {
    pub fn new(jwt: String, payload: &JwtPayload, subs: bool, taresult: bool) -> Self {
        VerifiedJWT {
            jwt,
            payload: payload.clone(),
            substatement: subs,
            taresult,
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct URL(String);
impl Deref for URL {
    type Target = String;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl Display for URL {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl Clone for URL {
    fn clone(&self) -> Self {
        URL(self.0.clone())
    }
}

#[derive(Debug, Deserialize)]
pub struct ServerConfiguration {
    pub domain: URL,
    pub redis_uri: String,
    pub tls_cert: Option<String>,
    pub tls_key: Option<String>,
    /// Allow HTTP scheme and private IPs in outbound federation requests (development only).
    pub allow_http: Option<bool>,
}

impl ServerConfiguration {
    pub fn new(
        domain: String,
        redis_uri: String,
        tls_cert: Option<String>,
        tls_key: Option<String>,
        allow_http: Option<bool>,
    ) -> ServerConfiguration {
        ServerConfiguration {
            domain: URL(domain),
            redis_uri,
            tls_cert,
            tls_key,
            allow_http,
        }
    }

    pub fn from_toml(toml_path: &str) -> Result<Self, Box<dyn StdError>> {
        let config_string = fs::read_to_string(toml_path)?;
        let intermediate: ServerConfiguration = toml::from_str(config_string.as_str())?;
        Ok(Self { ..intermediate })
    }

    // Constructs an instance of ServerConfiguration by fetching required values from env vars
    pub fn from_env() -> ServerConfiguration {
        let domain = env::var("TA_DOMAIN").unwrap_or("http://localhost:8080".to_string());
        let redis = env::var("TA_REDIS").unwrap_or("redis://redis:6379".to_string());
        let tls_cert = env::var("TA_TLS_CERT").ok();
        let tls_key = env::var("TA_TLS_KEY").ok();
        let allow_http = env::var("TA_ALLOW_HTTP")
            .ok()
            .map(|v| v == "true" || v == "1");
        ServerConfiguration::new(domain, redis, tls_cert, tls_key, allow_http)
    }
}

/// Creates a JWK Set from the public keys stored in the ./publickeys directory
pub fn get_ta_jwks_public_keyset() -> JwkSet {
    let mut keymap = Map::new();
    let mut keys: Vec<Value> = Vec::new();

    for public_keydata in PUBLIC_KEYS.iter() {
        if let Ok(publickey) = Jwk::from_bytes(public_keydata) {
            let map: Map<String, Value> = publickey.as_ref().clone();
            keys.push(json!(map));
        }
    }
    // Now outer map
    keymap.insert("keys".to_string(), json!(keys));

    JwkSet::from_map(keymap).expect("Failed to create JwkSet from public keys")
}

/// Generic function to create a signed JWT with the given payload, key, and optional token type.
///
/// This function supports signing with different key types (RSA, EC, OKP) and
/// algorithms (RS256, PS256, ES256, ES384, ES512, EdDSA for Ed25519/Ed448).
///
/// # Arguments
/// * `payload` - JwtPayload containing the JWT claims
/// * `key` - Jwk private key to sign with
/// * `token_type` - Optional JWT type (e.g., "resolve-response+jwt", "trust-mark-status-response+jwt")
///
/// # Returns
/// * `Result<String, JoseError>` - Serialized signed JWT string or error
pub fn create_signed_jwt(
    payload: &JwtPayload,
    key: &Jwk,
    token_type: Option<&str>,
) -> Result<String, JoseError> {
    create_signed_jwt_with_header(payload, key, token_type, None)
}

/// Same as `create_signed_jwt`, with an optional `trust_chain` JWS header
/// parameter per OpenID Federation §4.3. When `header_trust_chain` is
/// `Some(&[…])`, the header includes a `trust_chain` claim — an ordered
/// array of compact-serialised JWTs comprising the chain from the issuer's
/// subject up to a Trust Anchor.
///
/// Only inmor's `/resolve` response sets the header today (recipients of a
/// resolve response who want the chain can read either the payload's
/// `trust_chain` claim or this header). Subordinate Statements deliberately
/// omit it — the consumer of a subordinate statement walks the chain itself.
pub fn create_signed_jwt_with_header(
    payload: &JwtPayload,
    key: &Jwk,
    token_type: Option<&str>,
    header_trust_chain: Option<&[String]>,
) -> Result<String, JoseError> {
    let mut header = JwsHeader::new();
    header.set_token_type("JWT");

    // Set custom token type if provided
    if let Some(typ) = token_type {
        header.set_claim("typ", Some(json!(typ)))?;
    }

    // Spec §4.3 — embed the trust chain in the JWS header when requested.
    if let Some(chain) = header_trust_chain {
        header.set_claim("trust_chain", Some(json!(chain)))?;
    }

    // Get the algorithm from the key
    let alg = key.algorithm().unwrap_or("RS256");

    // Normalize algorithm name for josekit
    // josekit uses "EdDSA" for both Ed25519 and Ed448
    let normalized_alg = match alg {
        "Ed25519" | "Ed448" => "EdDSA",
        _ => alg,
    };

    header.set_claim("alg", Some(json!(normalized_alg)))?;

    // Set kid from the key — spec requires kid in all signed JWTs
    let kid = key.key_id().ok_or_else(|| {
        JoseError::InvalidKeyFormat(anyhow::anyhow!("Signing key must have a 'kid' field"))
    })?;
    header.set_key_id(kid);

    // For EdDSA keys, we need to create a modified key with alg="EdDSA"
    // because josekit's signer_from_jwk checks the alg field
    let signing_key = if alg == "Ed25519" || alg == "Ed448" {
        let mut key_map = key.as_ref().clone();
        key_map.insert("alg".to_string(), json!("EdDSA"));
        Jwk::from_map(key_map)?
    } else {
        key.clone()
    };

    // Create the appropriate signer based on the normalized algorithm
    let signer: Box<dyn JwsSigner> = match normalized_alg {
        "RS256" => Box::new(RS256.signer_from_jwk(&signing_key)?),
        "PS256" => Box::new(PS256.signer_from_jwk(&signing_key)?),
        "ES256" => Box::new(ES256.signer_from_jwk(&signing_key)?),
        "ES384" => Box::new(ES384.signer_from_jwk(&signing_key)?),
        "ES512" => Box::new(ES512.signer_from_jwk(&signing_key)?),
        "EdDSA" => Box::new(EdDSA.signer_from_jwk(&signing_key)?),
        _ => {
            // Default to RS256 if algorithm is not recognized
            Box::new(RS256.signer_from_jwk(&signing_key)?)
        }
    };

    let jwt = jwt::encode_with_signer(payload, &header, &*signer)?;
    Ok(jwt)
}

/// Returns entities from the collection data populated by inmor-collection.
/// If entity_type filter is given, reads from `inmor:collection:by_type:{type}` sets,
/// otherwise reads all from `inmor:collection:entities` hash.
async fn get_collection_entities(
    conn: &mut redis::aio::ConnectionManager,
    entity_types: &[String],
) -> Result<Vec<EntityCollectionResponse>> {
    let entity_ids: Vec<String> = if entity_types.is_empty() {
        // No filter: get all entity_ids from the hash
        redis::Cmd::hkeys("inmor:collection:entities")
            .query_async(conn)
            .await
            .unwrap_or_default()
    } else {
        // Get union of entity_ids across requested types
        let mut ids = HashSet::new();
        for etype in entity_types {
            validate_entity_type(etype)
                .map_err(|e| anyhow!("invalid entity_type '{}': {}", etype, e))?;
            let type_ids: Vec<String> =
                redis::Cmd::smembers(format!("inmor:collection:by_type:{etype}"))
                    .query_async(conn)
                    .await
                    .unwrap_or_default();
            ids.extend(type_ids);
        }
        ids.into_iter().collect()
    };

    let mut result = Vec::new();
    for eid in &entity_ids {
        let json_str: Option<String> = redis::Cmd::hget("inmor:collection:entities", eid)
            .query_async(conn)
            .await
            .ok();
        if let Some(json_str) = json_str
            && let Ok(entry) = serde_json::from_str::<EntityCollectionResponse>(&json_str)
        {
            result.push(entry);
        }
    }

    // Sort by entity_id for consistent ordering
    result.sort_by(|a, b| a.entity_id.cmp(&b.entity_id));
    Ok(result)
}

/// TODO: We need to deal with query parameters in future
/// https://openid.net/specs/openid-federation-1_0.html#section-8.2.1
#[get("/list")]
async fn list_subordinates(
    info: Query<SubListingParams>,
    redis: web::Data<redis::Client>,
) -> actix_web::Result<impl Responder> {
    let SubListingParams {
        entity_type,
        trust_marked,
        trust_mark_type,
        intermediate,
    } = info.into_inner();

    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    // This will contain all subordinates without filtering
    let mut results: Vec<EntityDetails> = Vec::new();
    {
        let entities = (redis::Cmd::hgetall("inmor:subordinates:jwt")
            .query_async::<HashMap<String, String>>(&mut conn)
            .await)
            .unwrap_or_default();

        for (key, val) in entities.iter() {
            // Let us get the metadata
            let (payload, _) = match get_unverified_payload_header(val) {
                Ok(d) => d,
                Err(e) => {
                    warn!("Failed to parse JWT for entity {}: {}", key, e);
                    continue; // Skip invalid JWTs instead of panicking
                }
            };
            let Some(metadata) = payload.claim("metadata") else {
                warn!("Missing metadata claim for entity: {}", key);
                continue; // Skip if no metadata
            };
            let trustmarks = payload.claim("trust_marks");
            let Some(x) = metadata.as_object() else {
                warn!("Metadata is not an object for entity: {}", key);
                continue; // Skip if metadata is not an object
            };
            // Collect all entity type identifiers present in metadata
            let entity_types: HashSet<String> = x.keys().cloned().collect();
            let entity = EntityDetails::new(key, entity_types, trustmarks);
            results.push(entity);
        }
    }
    // Now let us go through the list if we need to filter based on the query parameter.
    if let Some(etype) = entity_type {
        // Means one or more entity_type params were passed.
        // Keep entities that have at least one of the requested types.
        results.retain(|x| x.entity_types.iter().any(|t| etype.contains(t)));
    }

    if let Some(inter) = intermediate {
        // An intermediate is an entity with federation_entity metadata that also
        // has a federation_list_endpoint (i.e., it has subordinates). For simplicity
        // we filter on whether federation_entity is the *only* protocol type present
        // (no openid_provider, openid_relying_party, etc.).
        results.retain(|x| {
            let is_intermediate = x.entity_types.contains("federation_entity")
                && !x.entity_types.contains("openid_provider")
                && !x.entity_types.contains("openid_relying_party");
            if inter {
                is_intermediate
            } else {
                !is_intermediate
            }
        });
    }

    if let Some(true) = trust_marked {
        // Means check if at least one trustmark exists
        results.retain(|x| x.has_trustmark);
    }
    if let Some(trust_mark_type) = trust_mark_type {
        // Means filter based on trustmark type
        if let Err(e) = validate_redis_key_input(&trust_mark_type) {
            return error_response_400("invalid_request", &format!("invalid trust_mark_type: {e}"));
        }

        let query = format!("inmor:tmtype:{trust_mark_type}");
        let valid_entities: HashSet<String> = redis::Cmd::smembers(query)
            .query_async::<HashSet<String>>(&mut conn)
            .await
            .unwrap_or_default();
        results.retain(|x| valid_entities.contains(&x.entity_id));
    }

    let res: Vec<String> = results.iter().map(|x| x.entity_id.clone()).collect();
    Ok(HttpResponse::Ok().json(res))
}

/// https://zachmann.github.io/openid-federation-entity-collection/main.html
/// Entity collection endpoint. Reads data populated by inmor-collection CLI.
#[get("/collection")]
pub async fn fetch_collections(
    req: HttpRequest,
    redis: web::Data<redis::Client>,
) -> actix_web::Result<impl Responder> {
    let params: Vec<(String, String)> =
        match web::Query::<Vec<(String, String)>>::from_query(req.query_string()) {
            Ok(data) => data.to_vec(),
            Err(_) => Vec::new(),
        };

    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let mut entity_types: Vec<String> = Vec::new();

    // Parse query parameters
    for (q, p) in params.iter() {
        match q.as_str() {
            "entity_type" => {
                entity_types.push(p.clone());
            }
            _ => {
                return error_response_400("unsupported_parameter", q);
            }
        }
    }

    let result = get_collection_entities(&mut conn, &entity_types)
        .await
        .map_err(error::ErrorInternalServerError)?;

    // Get last_updated timestamp
    let last_updated: Option<u64> = redis::Cmd::get("inmor:collection:last_updated")
        .query_async(&mut conn)
        .await
        .ok();

    let response = json!({
        "entities": result,
        "last_updated": last_updated,
    });

    Ok(HttpResponse::Ok()
        .content_type("application/json")
        .body(response.to_string()))
}

/// https://openid.net/specs/openid-federation-1_0.html#name-fetch-subordinate-statement-
/// This will try to fetch a given subordinate's statement from the TA/I
#[get("/fetch")]
pub async fn fetch_subordinates(
    req: HttpRequest,
    redis: web::Data<redis::Client>,
) -> actix_web::Result<impl Responder> {
    let params = match web::Query::<HashMap<String, String>>::from_query(req.query_string()) {
        Ok(data) => data,
        Err(_) => return Err(error::ErrorBadRequest("Missing params")),
    };
    let sub = match params.get("sub") {
        Some(data) => data,
        None => return error_response_400("invalid_request", "Missing required parameter: sub"),
    };

    // After we have the query
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let res = match redis::Cmd::hget("inmor:subordinates", sub)
        .query_async::<String>(&mut conn)
        .await
    {
        Ok(data) => data,
        Err(e) => {
            warn!("Subordinate not found in Redis for sub={}: {}", sub, e);
            return error_response_404("not_found", "Subordinate not found.");
        }
    };

    Ok(HttpResponse::Ok()
        .content_type("application/entity-statement+jwt")
        .body(res))
}

/// Get JWK Set from the given payload
pub fn get_jwks_from_payload(payload: &JwtPayload) -> Result<JwkSet> {
    let jwks_data = match payload.claim("jwks") {
        Some(data) => data,
        None => {
            debug!("No jwks claim found in payload");
            return Err(anyhow::Error::msg("No jwks was found in the payload"));
        }
    };
    let keys = match jwks_data.get("keys") {
        Some(data) => data,
        None => {
            debug!("No keys field found in jwks claim");
            return Err(anyhow::Error::msg(
                "No keys was found in jwks in the payload",
            ));
        }
    };
    let mut internal_map: Map<String, Value> = Map::new();
    internal_map.insert("keys".to_string(), keys.clone());

    Ok(JwkSet::from_map(internal_map)?)
}

/// Fetch a JWKS from a remote `jwks_uri` endpoint.
///
/// Uses the shared HTTP client with the same URL validation and size limits
/// as other federation requests.
pub async fn fetch_jwks_from_uri(uri: &str) -> Result<JwkSet> {
    let body = get_query(uri).await?;
    parse_jwks_json(&body).map_err(|e| anyhow!("Failed to parse JWKS from {}: {}", uri, e))
}

/// Fetch a JWKS from a URI with Redis caching.
///
/// Checks Redis for a cached copy first. On cache miss, fetches from the URI,
/// stores in Redis with a 1-hour TTL, and returns the key set.
pub async fn get_jwks_from_uri_cached(
    uri: &str,
    conn: &mut redis::aio::ConnectionManager,
) -> Result<JwkSet> {
    let hash = Sha256::digest(uri);
    let cache_key = format!("inmor:jwks_cache:{:x}", hash);

    // Try cache first
    let cached: Option<String> = redis::Cmd::get(&cache_key)
        .query_async(conn)
        .await
        .unwrap_or(None);

    if let Some(ref cached_json) = cached {
        return parse_jwks_json(cached_json);
    }

    // Cache miss — fetch from URI
    let body = get_query(uri).await?;
    let keyset = parse_jwks_json(&body)?;

    // Store raw JSON in Redis with 1-hour TTL
    let _: Result<(), _> = redis::Cmd::set_ex(&cache_key, &body, 3600)
        .query_async(conn)
        .await;

    Ok(keyset)
}

/// Fetch a JWKS from a remote `signed_jwks_uri` endpoint.
///
/// Per OpenID Federation §5.2.1, the response body is a JWT whose payload is
/// a JWKS, signed by a key contained in that same JWKS (self-verifying, same
/// pattern as an Entity Configuration's self-signature). The signed form is
/// strictly stronger than a plain `jwks_uri` because the response is
/// authenticated against keys the entity itself controls.
///
/// Verification flow:
/// 1. Fetch the JWT via the shared HTTP client (SSRF gate, body cap, timeouts).
/// 2. Parse the payload unverified to extract the inner JWKS.
/// 3. Look up the JWT's `kid` in that inner JWKS.
/// 4. Verify the JWT against the inner JWKS using `verify_jwt_with_jwks`
///    (signature + temporal validation + `crit` check).
///
/// Caching is intentionally NOT performed yet — a Redis cache parallel to
/// the existing `inmor:jwks_cache:*` entries is planned. The HTML coverage
/// page records this as future work.
pub async fn fetch_signed_jwks_from_uri(uri: &str) -> Result<JwkSet> {
    let body = get_query(uri).await?;
    verify_signed_jwks_body(&body).map_err(|e| anyhow!("signed_jwks_uri {uri}: {e}"))
}

/// Verification half of `fetch_signed_jwks_from_uri`, split out so unit
/// tests can exercise the cryptographic logic without an HTTP fixture.
///
/// `body` is the compact-serialised signed-JWKS JWT. Returns the inner
/// JWKS only after confirming the JWT was signed by a key it contains and
/// that signature, temporal, and `crit` checks all pass.
pub fn verify_signed_jwks_body(body: &str) -> Result<JwkSet> {
    let (payload, _header) =
        get_unverified_payload_header(body).map_err(|e| anyhow!("body is not a JWT: {e}"))?;
    let inner_jwks = get_jwks_from_payload(&payload)
        .map_err(|e| anyhow!("payload missing inner `jwks` claim: {e}"))?;
    let (_verified_payload, _header) = verify_jwt_with_jwks(body, Some(inner_jwks.clone()))
        .map_err(|e| anyhow!("signature / temporal check failed: {e}"))?;
    Ok(inner_jwks)
}

/// Parse a JWKS JSON string into a JwkSet.
fn parse_jwks_json(json_str: &str) -> Result<JwkSet> {
    let parsed: Value =
        serde_json::from_str(json_str).map_err(|e| anyhow!("Invalid JWKS JSON: {}", e))?;
    let keys = parsed
        .get("keys")
        .ok_or_else(|| anyhow!("No 'keys' field in JWKS"))?;
    let mut internal_map: Map<String, Value> = Map::new();
    internal_map.insert("keys".to_string(), keys.clone());
    Ok(JwkSet::from_map(internal_map)?)
}

/// Try to get JWKS from the payload's `jwks` claim, falling back to
/// `signed_jwks_uri`, then to plain `jwks_uri`.
///
/// Priority: inline `jwks` > `signed_jwks_uri` > `jwks_uri`.
///
/// **Downgrade-fallback note** — when `signed_jwks_uri` is present but its
/// fetch or signature verification fails, this helper falls back to plain
/// `jwks_uri` if one is also present. That is operator-chosen behavior to
/// preserve resilience during signed-JWKS rollout; it is **not** spec
/// strict-compliance. A network attacker who can disrupt the signed-JWKS
/// path (e.g., 5xx the host) AND tamper with the unsigned path can force
/// the downgrade. Operators who do not want this should not configure a
/// plain `jwks_uri` alongside `signed_jwks_uri`.
pub async fn get_jwks_from_payload_or_uri(
    payload: &JwtPayload,
    conn: &mut redis::aio::ConnectionManager,
) -> Result<JwkSet> {
    // Try inline jwks first.
    if let Ok(keyset) = get_jwks_from_payload(payload) {
        return Ok(keyset);
    }

    // Then signed_jwks_uri — stronger guarantee, so preferred over plain.
    if let Some(uri_value) = payload.claim("signed_jwks_uri")
        && let Some(uri) = uri_value.as_str()
    {
        debug!("No inline jwks, fetching from signed_jwks_uri: {}", uri);
        match fetch_signed_jwks_from_uri(uri).await {
            Ok(keyset) => return Ok(keyset),
            Err(e) => {
                warn!("signed_jwks_uri {uri} failed: {e}; falling back to jwks_uri if present");
                // fall through to plain jwks_uri attempt below
            }
        }
    }

    // Fall back to plain jwks_uri.
    if let Some(uri_value) = payload.claim("jwks_uri")
        && let Some(uri) = uri_value.as_str()
    {
        debug!("Fetching from jwks_uri: {}", uri);
        return get_jwks_from_uri_cached(uri, conn).await;
    }

    Err(anyhow!(
        "No jwks, signed_jwks_uri, or jwks_uri found in payload"
    ))
}

/// Gets the payload and header without any cryptographic verification.
#[allow(clippy::explicit_counter_loop)]
pub fn get_unverified_payload_header(data: &str) -> Result<(JwtPayload, JwsHeader)> {
    let mut indexies: Vec<usize> = Vec::new();
    let mut i: usize = 0;
    for d in data.as_bytes().iter() {
        if *d == b'.' {
            indexies.push(i);
        }
        i += 1;
    }

    let input = data.as_bytes();
    if indexies.len() != 2 {
        return Err(anyhow::Error::msg(
            "The compact serialization form of JWS must be three parts separated by colon.",
        ));
    }

    let header = &input[0..indexies[0]];
    let payload = &input[(indexies[0] + 1)..(indexies[1])];
    let header = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(header)
        .map_err(|e| anyhow::Error::msg(format!("Failed to decode header: {}", e)))?;
    let header: Map<String, Value> = serde_json::from_slice(&header)
        .map_err(|e| anyhow::Error::msg(format!("Failed to parse header JSON: {}", e)))?;
    let header = JwsHeader::from_map(header)
        .map_err(|e| anyhow::Error::msg(format!("Failed to create JwsHeader: {}", e)))?;
    let payload = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(payload)
        .map_err(|e| anyhow::Error::msg(format!("Failed to decode payload: {}", e)))?;
    let map: Map<String, Value> = serde_json::from_slice(&payload)
        .map_err(|e| anyhow::Error::msg(format!("Failed to parse payload JSON: {}", e)))?;
    let payload = JwtPayload::from_map(map)
        .map_err(|e| anyhow::Error::msg(format!("Failed to create JwtPayload: {}", e)))?;
    // End of stupid unverified code
    Ok((payload, header))
}

/// Verify JWT *signature only* against the given JWKS (or the JWT's own inline
/// `jwks` claim if `keys` is `None`). Does NOT validate temporal claims
/// (`exp`/`nbf`/`iat`).
///
/// Callers that need both signature and temporal validation should use
/// `verify_jwt_with_jwks`. Splitting these is useful when the caller needs to
/// distinguish "bad signature" from "expired", e.g. `trust_mark_status`, which
/// must return different status codes for the two cases.
pub fn verify_jwt_signature_with_jwks(
    data: &str,
    keys: Option<JwkSet>,
) -> Result<(JwtPayload, JwsHeader)> {
    let (payload, header) = get_unverified_payload_header(data)?;
    let jwks = match keys {
        Some(d) => d,
        None => get_jwks_from_payload(&payload)?,
    };
    let kid = header
        .key_id()
        .ok_or_else(|| anyhow::Error::msg("Missing key ID in JWT header"))?;
    let keys = jwks.get(kid);
    if keys.is_empty() {
        return Err(anyhow::Error::msg("Can not find kid used to sign."));
    }
    let key = keys[0];
    let algorithm = header
        .algorithm()
        .ok_or_else(|| anyhow::Error::msg("Missing algorithm in JWT header"))?;
    // Per spec Section 7.3: alg MUST NOT be "none"
    if algorithm == "none" {
        return Err(anyhow::Error::msg("Algorithm 'none' is not permitted"));
    }
    let boxed_verifier: Box<dyn JwsVerifier> = match algorithm {
        "RS256" => Box::new(RS256.verifier_from_jwk(key)?),
        "PS256" => Box::new(PS256.verifier_from_jwk(key)?),
        "ES256" => Box::new(ES256.verifier_from_jwk(key)?),
        "ES384" => Box::new(ES384.verifier_from_jwk(key)?),
        "ES512" => Box::new(ES512.verifier_from_jwk(key)?),
        "EdDSA" => Box::new(EdDSA.verifier_from_jwk(key)?),
        _ => {
            return Err(anyhow::Error::msg(format!(
                "Unsupported algorithm: {}",
                algorithm
            )));
        }
    };
    let verifier = &*boxed_verifier;
    let (payload, header) = jwt::decode_with_verifier(data, verifier)?;
    Ok((payload, header))
}

/// Verify JWT against given JWKS (signature + temporal claims + `crit`).
///
/// Per OpenID Federation §3.1.1, the `crit` claim lists claim names that
/// recipients MUST understand. We reject anything whose `crit` contains a
/// name not in `KNOWN_CLAIMS`. The chain walker treats this as a normal
/// verification failure and skips the offending authority via `continue`.
pub fn verify_jwt_with_jwks(data: &str, keys: Option<JwkSet>) -> Result<(JwtPayload, JwsHeader)> {
    let (payload, header) = verify_jwt_signature_with_jwks(data, keys)?;
    // See more https://github.com/SUNET/inmor/issues/79
    let mut validator = JwtPayloadValidator::new();
    validator.set_base_time(SystemTime::now());
    validator.validate(&payload)?;
    enforce_crit_claim(&payload)?;
    Ok((payload, header))
}

/// Reject a statement whose `crit` claim references a name we don't understand.
///
/// Spec §3.1.1: `crit` is an array of claim names the issuer requires the
/// recipient to understand. We compare each entry against `KNOWN_CLAIMS`;
/// any unknown entry means we cannot safely process this statement and MUST
/// reject it. A missing `crit` claim is fine — issuers aren't required to
/// set one.
fn enforce_crit_claim(payload: &JwtPayload) -> Result<()> {
    let Some(crit_value) = payload.claim("crit") else {
        return Ok(());
    };
    let Some(entries) = crit_value.as_array() else {
        bail!("crit claim must be a JSON array of strings");
    };
    for entry in entries {
        let Some(name) = entry.as_str() else {
            bail!("crit claim contains non-string entry: {entry:?}");
        };
        if !KNOWN_CLAIMS.contains(&name) {
            bail!("unknown critical claim: {name}");
        }
    }
    Ok(())
}

/// Verify a self-signed entity configuration JWT.
///
/// Verifies the signature against the `jwks` claim inside the JWT itself, then
/// enforces the OpenID Federation §3.1 invariant that an entity configuration's
/// `iss` and `sub` MUST be equal. Without that check, an entity that controls a
/// signing key could mint a self-signed JWT claiming a different `sub`.
///
/// Callers MUST only pass entity configurations to this function. Subordinate
/// statements and trust marks have different signing semantics and require the
/// authority's JWKS (see `verify_jwt_with_jwks`).
pub fn self_verify_jwt(data: &str) -> Result<(JwtPayload, JwsHeader)> {
    let (payload, _header) = get_unverified_payload_header(data)?;
    let jwks = get_jwks_from_payload(&payload)?;
    let (payload, header) = verify_jwt_with_jwks(data, Some(jwks))?;

    // Spec §3.1: Entity Configuration MUST have iss == sub. Reject anything
    // else so a forged sub can never ride through on a valid signature.
    let iss = payload.issuer().unwrap_or("");
    let sub = payload.subject().unwrap_or("");
    if iss.is_empty() || sub.is_empty() || iss != sub {
        bail!("self_verify_jwt: entity configuration iss ({iss:?}) != sub ({sub:?}) (spec §3.1)");
    }

    Ok((payload, header))
}

/// OpenID Federation §6.2 `constraints` parsed from a Subordinate Statement
/// (or an Entity Configuration). Each Subordinate Statement's constraints
/// apply to its subject and any entity below it in the chain.
///
/// Inmor's walker checks each successfully-verified Subordinate Statement's
/// constraints against the resolve subject (the chain leaf). A violation
/// causes the offending authority to be skipped — same `continue` pattern
/// as a bad signature or missing JWKS.
#[derive(Debug, Clone, Default)]
pub struct Constraints {
    /// §6.2.1 — maximum number of entities allowed below the SS subject in
    /// the chain. `None` means no constraint set by this statement.
    pub max_path_length: Option<u8>,
    /// §6.2.2 — URL subtrees the subject MUST be a subordinate of (any one
    /// match within this list suffices; empty list means no constraint set
    /// by this statement).
    pub permitted_subtrees: Vec<String>,
    /// §6.2.2 — URL subtrees the subject MUST NOT be a subordinate of.
    pub excluded_subtrees: Vec<String>,
    /// §6.2.3 — entity types allowed for any entity below the SS subject in
    /// the chain. `None` means no constraint set.
    pub allowed_entity_types: Option<Vec<String>>,
    /// §6.2.3 — entity types allowed specifically for leaf entities (those
    /// with no further subordinates). `None` means no constraint set.
    pub allowed_leaf_entity_types: Option<Vec<String>>,
}

impl Constraints {
    /// Parse a `constraints` claim out of a JWT payload.
    ///
    /// * Absent `constraints` returns `Ok(Self::default())` — no constraint
    ///   set by this statement is valid.
    /// * Present but malformed `constraints` (non-object, wrong field types,
    ///   `max_path_length` out of `u8` range, non-string entries inside an
    ///   array) returns `Err(...)`. The walker treats that error as a
    ///   verification failure and skips the offending authority, so a
    ///   constraint issuer cannot disable enforcement by sending a broken
    ///   `constraints` object.
    pub fn from_payload(payload: &JwtPayload) -> Result<Self> {
        let Some(c) = payload.claim("constraints") else {
            return Ok(Self::default());
        };
        let Some(obj) = c.as_object() else {
            bail!("constraints claim must be a JSON object");
        };
        let max_path_length = match obj.get("max_path_length") {
            None => None,
            Some(v) => {
                let n = v.as_u64().ok_or_else(|| {
                    anyhow!("constraints.max_path_length must be a non-negative integer")
                })?;
                Some(u8::try_from(n).map_err(|_| {
                    anyhow!("constraints.max_path_length {n} out of u8 range (0..=255)")
                })?)
            }
        };
        let pull_string_array = |key: &str| -> Result<Vec<String>> {
            let Some(v) = obj.get(key) else {
                return Ok(Vec::new());
            };
            let arr = v
                .as_array()
                .ok_or_else(|| anyhow!("constraints.{key} must be an array of strings"))?;
            arr.iter()
                .map(|e| {
                    e.as_str()
                        .map(str::to_string)
                        .ok_or_else(|| anyhow!("constraints.{key} contains non-string entry"))
                })
                .collect()
        };
        let pull_opt_string_array = |key: &str| -> Result<Option<Vec<String>>> {
            let Some(v) = obj.get(key) else {
                return Ok(None);
            };
            let arr = v
                .as_array()
                .ok_or_else(|| anyhow!("constraints.{key} must be an array of strings"))?;
            arr.iter()
                .map(|e| {
                    e.as_str()
                        .map(str::to_string)
                        .ok_or_else(|| anyhow!("constraints.{key} contains non-string entry"))
                })
                .collect::<Result<Vec<_>>>()
                .map(Some)
        };
        Ok(Self {
            max_path_length,
            permitted_subtrees: pull_string_array("permitted_subtrees")?,
            excluded_subtrees: pull_string_array("excluded_subtrees")?,
            allowed_entity_types: pull_opt_string_array("allowed_entity_types")?,
            allowed_leaf_entity_types: pull_opt_string_array("allowed_leaf_entity_types")?,
        })
    }

    /// Check the resolve subject against these constraints.
    ///
    /// `chain_entities_below` is the number of entities below the SS subject
    /// in the chain — equivalently the walker `depth` when this SS is being
    /// processed (depth=0 means the SS is directly about the leaf).
    ///
    /// Composition note: when multiple Subordinate Statements set
    /// constraints, the spec mandates the intersection / strictest. Inmor
    /// reaches that effect by checking each SS independently against the
    /// leaf — if any single SS would reject the leaf, the chain is rejected
    /// at that hop. The walker's `continue` then forces the resolver to try
    /// alternative authority branches if any exist.
    pub fn check_subject(
        &self,
        subject: &str,
        subject_entity_types: &HashSet<String>,
        is_leaf: bool,
        chain_entities_below: u8,
    ) -> Result<()> {
        if let Some(max) = self.max_path_length
            && chain_entities_below > max
        {
            bail!(
                "max_path_length {max} exceeded: {chain_entities_below} entities below SS subject"
            );
        }
        if !self.permitted_subtrees.is_empty() {
            let any = self
                .permitted_subtrees
                .iter()
                .any(|s| is_subordinate_of(subject, s));
            if !any {
                bail!("subject {subject} not under any permitted_subtree");
            }
        }
        if let Some(bad) = self
            .excluded_subtrees
            .iter()
            .find(|s| is_subordinate_of(subject, s))
        {
            bail!("subject {subject} under excluded_subtree {bad}");
        }
        if let Some(allowed) = &self.allowed_entity_types {
            // A subject with no declared metadata keys has no way to satisfy
            // an allowlist constraint — fail closed so a subject can't bypass
            // an entity-type restriction by simply omitting `metadata`.
            if subject_entity_types.is_empty() {
                bail!("allowed_entity_types is set but subject has no declared entity types");
            }
            let allowed_set: HashSet<&str> = allowed.iter().map(String::as_str).collect();
            for t in subject_entity_types {
                if !allowed_set.contains(t.as_str()) {
                    bail!("subject entity_type {t} not in allowed_entity_types");
                }
            }
        }
        if is_leaf && let Some(allowed) = &self.allowed_leaf_entity_types {
            // Same fail-closed treatment for the leaf-only variant.
            if subject_entity_types.is_empty() {
                bail!("allowed_leaf_entity_types is set but leaf has no declared entity types");
            }
            let allowed_set: HashSet<&str> = allowed.iter().map(String::as_str).collect();
            for t in subject_entity_types {
                if !allowed_set.contains(t.as_str()) {
                    bail!("leaf entity_type {t} not in allowed_leaf_entity_types");
                }
            }
        }
        Ok(())
    }
}

/// Spec §6.2.2 — is `entity_url` a subordinate of the URL `subtree`?
///
/// Matching rules:
/// * scheme + host are compared case-insensitively
/// * port matches by `port_or_known_default` (so implicit 443 == explicit 443)
/// * `subtree`'s path MUST be a prefix of `entity_url`'s path at a
///   path-segment boundary — `https://e.com/fed` matches `https://e.com/fed/leaf`
///   but NOT `https://e.com/fed2`
/// * trailing slashes are normalized (`/fed` ≡ `/fed/`)
/// * `subtree` MUST NOT contain a query or fragment; either makes the
///   subtree malformed and the function returns false
/// * `entity_url`'s query and fragment are ignored
pub fn is_subordinate_of(entity_url: &str, subtree: &str) -> bool {
    let Ok(e) = url::Url::parse(entity_url) else {
        return false;
    };
    let Ok(s) = url::Url::parse(subtree) else {
        return false;
    };
    if s.query().is_some() || s.fragment().is_some() {
        return false;
    }
    if !e.scheme().eq_ignore_ascii_case(s.scheme()) {
        return false;
    }
    let e_host = e.host_str().map(str::to_ascii_lowercase);
    let s_host = s.host_str().map(str::to_ascii_lowercase);
    if e_host != s_host {
        return false;
    }
    if e.port_or_known_default() != s.port_or_known_default() {
        return false;
    }
    let e_path = e.path().trim_end_matches('/');
    let s_path = s.path().trim_end_matches('/');
    if s_path.is_empty() {
        // Subtree spans the entire host.
        return true;
    }
    if !e_path.starts_with(s_path) {
        return false;
    }
    let rest = &e_path[s_path.len()..];
    rest.is_empty() || rest.starts_with('/')
}

/// Per-walk state carried through `resolve_entity_to_trustanchor`.
///
/// Holds the resolve subject's identity (for §6.2 constraint checks
/// against the chain leaf) and the wall-clock deadline for chain fetches
/// (§10.5).
#[derive(Debug, Clone)]
pub struct WalkContext {
    pub original_subject: String,
    pub original_subject_entity_types: HashSet<String>,
    /// Wall-clock deadline for outbound chain fetches. The walker checks
    /// this before each fetch; exceeding it surfaces as a transient
    /// failure to `/resolve` (HTTP 503 + `Retry-After`).
    pub fetch_deadline: SystemTime,
}

impl WalkContext {
    /// Build a context from the resolve subject's self-verified Entity
    /// Configuration payload. Entity types are read from `metadata`'s keys
    /// (each top-level key in `metadata` is an entity-type identifier per
    /// §5.1). The fetch deadline is set to now + `CHAIN_FETCH_BUDGET_SECS`.
    pub fn from_subject_payload(subject: &str, payload: &JwtPayload) -> Self {
        let entity_types = payload
            .claim("metadata")
            .and_then(|m| m.as_object())
            .map(|m| m.keys().cloned().collect())
            .unwrap_or_default();
        Self {
            original_subject: subject.to_string(),
            original_subject_entity_types: entity_types,
            fetch_deadline: SystemTime::now() + Duration::from_secs(CHAIN_FETCH_BUDGET_SECS),
        }
    }
}

/// Maximum recursion depth for trust chain resolution.
/// Practical federations rarely exceed 3-4 levels. Kept independent of
/// §6.2.1 `max_path_length` as a defense-in-depth backstop.
const MAX_RESOLVE_DEPTH: u8 = 10;

/// Return `Err(FetchError::transient)` if the walk context's deadline has
/// passed. Called immediately before every outbound fetch inside the
/// walker so a single frame can't busy-loop past the §10.5 budget.
fn check_chain_fetch_budget(ctx: Option<&WalkContext>, sub: &str) -> Result<()> {
    if let Some(c) = ctx
        && SystemTime::now() > c.fetch_deadline
    {
        return Err(anyhow::Error::new(FetchError::transient(
            None,
            format!("chain-fetch budget of {CHAIN_FETCH_BUDGET_SECS}s exceeded for {sub}"),
        )));
    }
    Ok(())
}

/// Maximum number of trust marks the resolver will verify per /resolve request.
/// Each external-issued mark may trigger up to two outbound HTTP requests
/// (each capped by `HTTP_CLIENT`'s 10s timeout); an attacker-controlled subject
/// entity configuration can otherwise embed hundreds of marks and stall an
/// actix worker. Practical entities carry a handful of marks.
const MAX_TRUST_MARKS_PER_RESOLVE: usize = 32;

/// Total wall-clock budget for the trust-mark verification phase of /resolve.
/// Bounds worst-case worker-thread time even when every mark hits its per-request
/// timeout. The budget intentionally exceeds a single mark's worst-case latency
/// (~20s) so a single slow issuer doesn't starve the rest.
const TRUST_MARK_VERIFICATION_BUDGET_SECS: u64 = 30;

/// Build the trust chain for `sub` up to one of `trust_anchors`.
///
/// **Return contract**: `Ok(vec)` does NOT mean the chain reached a trust
/// anchor. On a fetch or verification failure mid-walk the function returns
/// the partial chain accumulated so far (possibly an empty vec) so that
/// callers can still try alternative authority hints. Callers MUST verify
/// completeness before trusting the result:
///
/// 1. `!vec.is_empty()` — chain has at least one entry.
/// 2. `vec.iter().any(|e| e.taresult)` — the chain actually terminates at a
///    requested trust anchor.
///
/// `/resolve` (see `resolve_entity` below) enforces both checks and returns
/// 400 `invalid_trust_chain` otherwise. The recursive caller inside this
/// function continues to the next authority hint on a partial result via the
/// `r_result.is_empty()` check below.
pub async fn resolve_entity_to_trustanchor(
    sub: &str,
    trust_anchors: Vec<&str>,
    start: bool,
    visited: &mut HashSet<String>,
    depth: u8,
    redis_conn: &mut redis::aio::ConnectionManager,
    ctx: Option<&WalkContext>,
) -> Result<Vec<VerifiedJWT>> {
    if depth > MAX_RESOLVE_DEPTH {
        bail!(
            "Trust chain resolution exceeded maximum depth of {}",
            MAX_RESOLVE_DEPTH
        );
    }
    debug!("Received {sub} with trust anchors {trust_anchors:?}");

    // Spec §10.5 — chain-fetch deadline. We check the deadline once per
    // walker invocation AND immediately before each outbound fetch in this
    // frame. Without the per-fetch checks, a single recursion-frame loop
    // over many authority_hints could blow past the budget before the
    // next recursion's entry check fires.
    check_chain_fetch_budget(ctx, sub)?;

    let empty_authority: Vec<String> = Vec::new();
    let eal = json!(empty_authority);

    // This will hold the list of trust chain
    let mut result = Vec::new();

    // to stop infinite loop
    // First get the entity configuration and self verify
    let original_ec = match get_entity_configruation_as_jwt(sub).await {
        Ok(res) => res,
        Err(e) => {
            warn!("Failed to fetch entity configuration for {}: {}", sub, e);
            // Transient fetch failures bubble up so /resolve can emit 503.
            // Permanent failures keep the legacy partial-chain behaviour
            // (callers inspect `found_ta`).
            if e.downcast_ref::<FetchError>().is_some_and(|f| f.transient) {
                return Err(e);
            }
            return Ok(result); // Read FOUND_TA section in code to find why it is okay to
            // result a half done list back.
        }
    };
    // Add it already visited
    visited.insert(sub.to_string());

    let (opayload, _oheader) = self_verify_jwt(&original_ec)?;

    if start {
        let vjwt = VerifiedJWT::new(original_ec.clone(), &opayload, false, false);
        result.push(vjwt);
    }

    // Spec §6.2: constraints in a Subordinate Statement apply to entities
    // below the SS subject. We check each SS independently against the
    // resolve subject (chain leaf). The walk context carries the leaf's
    // identity and declared entity types; built on the outermost call from
    // the leaf's self-verified EC.
    let owned_ctx;
    let walk_ctx: &WalkContext = match ctx {
        Some(c) => c,
        None => {
            owned_ctx = WalkContext::from_subject_payload(sub, &opayload);
            &owned_ctx
        }
    };

    // Now find the authority_hints
    let authority_hints = match opayload.claim("authority_hints") {
        Some(v) => v,
        // Means we are at one Trust anchor (most probably)
        None => &eal,
    };
    debug!("Authority hints: {authority_hints:?}");
    // Loop over the authority hints
    let Some(ah_array) = authority_hints.as_array() else {
        return Ok(result); // Return if not an array
    };
    for ah in ah_array {
        // Flag to mark if we found the trust anchor
        let mut ta_flag = false;
        // Get the str from the JSON value
        let Some(ah_entity) = ah.as_str() else {
            continue; // Skip if not a string
        };
        // If we already visited the authority then continue
        if visited.contains(ah_entity) {
            continue;
        }
        // If this is one of the trust anchor, then we are done
        if trust_anchors.contains(&ah_entity) {
            // Means we found our trust anchor
            ta_flag = true;
        }
        // §10.5 — re-check budget before each outbound fetch in the loop.
        check_chain_fetch_budget(Some(walk_ctx), sub)?;
        // Fetch the authority's entity configuration
        let ah_jwt = match get_entity_configruation_as_jwt(ah_entity).await {
            Ok(res) => res,
            Err(e) => {
                warn!(
                    "Failed to fetch authority entity configuration for {}: {}",
                    ah_entity, e
                );
                if e.downcast_ref::<FetchError>().is_some_and(|f| f.transient) {
                    return Err(e);
                }
                return Ok(result); // Read FOUND_TA section in code to find why it is okay to
                // result a half done list back.
            }
        };

        // Verify and get the payload
        let jwt_result = self_verify_jwt(&ah_jwt);
        if jwt_result.is_err() {
            warn!(
                "Failed to verify authority JWT for {}: {:?}",
                ah_entity,
                jwt_result.err()
            );
            continue;
        }

        let (ah_payload, _) = jwt_result.expect("This can not be error here.");
        let Some(ah_metadata) = ah_payload.claim("metadata") else {
            warn!("Missing metadata in authority payload for: {}", ah_entity);
            continue;
        };
        let Some(federation_entity) = ah_metadata.get("federation_entity") else {
            warn!("Missing federation_entity in metadata for: {}", ah_entity);
            continue;
        };
        let Some(fetch_endpoint) = federation_entity.get("federation_fetch_endpoint") else {
            warn!("Missing federation_fetch_endpoint for: {}", ah_entity);
            continue;
        };
        let Some(fetch_endpoint_str) = fetch_endpoint.as_str() else {
            warn!(
                "federation_fetch_endpoint is not a string for: {}",
                ah_entity
            );
            continue;
        };
        // §10.5 — re-check budget before each outbound fetch.
        check_chain_fetch_budget(Some(walk_ctx), sub)?;
        // Fetch the entity statement/ subordinate statement
        let sub_statement = match fetch_subordinate_statement(fetch_endpoint_str, sub).await {
            Ok(res) => res,
            Err(e) => {
                warn!(
                    "Failed to fetch subordinate statement for {} from {}: {}",
                    sub, ah_entity, e
                );
                if e.downcast_ref::<FetchError>().is_some_and(|f| f.transient) {
                    return Err(e);
                }
                return Ok(result); // Read FOUND_TA section in code to find why it is okay to
                // result a half done list back.
            }
        };
        // Get the authority's JWKS (inline, or via jwks_uri fallback) and verify the subordinate statement.
        let ah_jwks = match get_jwks_from_payload_or_uri(&ah_payload, redis_conn).await {
            Ok(result) => result,
            Err(e) => {
                warn!(
                    "Failed to get JWKS from authority payload for {}: {}",
                    ah_entity, e
                );
                continue;
            }
        };
        let (subs_payload, _) = match verify_jwt_with_jwks(&sub_statement, Some(ah_jwks)) {
            Ok(value) => value,
            Err(e) => {
                warn!(
                    "Failed to verify subordinate statement for {} from {}: {}",
                    sub, ah_entity, e
                );
                continue;
            }
        };

        // Spec §3.2: ES[j] MUST be signed by a key in ES[j+1].jwks. We bind by
        // key material, not by `kid`: re-verify the subject's self-EC against
        // the subordinate statement's authoritative `jwks`. A successful
        // signature check proves the actual signing key is present in that
        // JWKS. Matching on `kid` strings alone would let an authority list a
        // different key under the same `kid` and bypass the chain-link check.
        let ss_jwks = match get_jwks_from_payload(&subs_payload) {
            Ok(j) => j,
            Err(e) => {
                warn!(
                    "trust chain: subordinate statement from {ah_entity} for {sub} has no usable jwks ({e}); skipping authority"
                );
                continue;
            }
        };
        if let Err(e) = verify_jwt_with_jwks(&original_ec, Some(ss_jwks)) {
            warn!(
                "trust chain: {sub} EC not signed by any key in subordinate statement jwks from {ah_entity} ({e}); skipping authority"
            );
            continue;
        }

        // Spec §6.2: enforce the Subordinate Statement's `constraints`
        // (max_path_length, permitted/excluded_subtrees, allowed entity
        // types) against the resolve subject. `depth` at this point is the
        // number of entities below `sub` in the chain (depth=0 means `sub`
        // is the leaf and the SS is directly about it).
        let ss_constraints = match Constraints::from_payload(&subs_payload) {
            Ok(c) => c,
            Err(e) => {
                // Malformed `constraints` is a verification failure for
                // this SS — refuse to silently disable enforcement.
                warn!(
                    "trust chain: malformed constraints in subordinate statement from {ah_entity} ({e}); skipping authority"
                );
                continue;
            }
        };
        let is_leaf = depth == 0;
        if let Err(e) = ss_constraints.check_subject(
            &walk_ctx.original_subject,
            &walk_ctx.original_subject_entity_types,
            is_leaf,
            depth,
        ) {
            warn!(
                "trust chain: constraints in subordinate statement from {ah_entity} reject {sub} ({e}); skipping authority"
            );
            continue;
        }

        if ta_flag {
            // Means this is the end of resolving
            let vjwt = VerifiedJWT::new(sub_statement, &subs_payload, true, false);
            result.push(vjwt);
            let ajwt = VerifiedJWT::new(ah_jwt.clone(), &ah_payload, false, true);
            result.push(ajwt);
            return Ok(result);
        } else {
            // §10.5 — budget check before descending one more level so a
            // pathological intermediate can't burn the whole budget on
            // recursive fetches before bailing out.
            check_chain_fetch_budget(Some(walk_ctx), sub)?;
            // Now do a recursive query
            let r_result = Box::pin(resolve_entity_to_trustanchor(
                ah_entity,
                trust_anchors.clone(),
                false,
                visited,
                depth + 1,
                redis_conn,
                Some(walk_ctx),
            ))
            .await?;
            if r_result.is_empty() {
                continue;
            } else {
                let vjwt = VerifiedJWT::new(sub_statement, &subs_payload, true, false);
                result.push(vjwt);
                result.extend(r_result);
            }
            return Ok(result);
        }
    }
    Ok(vec![])
}

/// To create the signed JWT for resolve response
/// Per spec Section 8.3.2, the `exp` MUST be the minimum of the `exp` values
/// from the Trust Chain and any Trust Marks included in the response.
fn create_resolve_response_jwt(
    state: &web::Data<AppState>,
    sub: &str,
    result: &[VerifiedJWT],
    metadata: Option<Map<String, Value>>,
    trust_marks: Option<Vec<Value>>,
) -> Result<String, JoseError> {
    let mut payload = JwtPayload::new();
    let iss = state.entity_id.clone();
    payload.set_issuer(iss);
    payload.set_subject(sub);
    payload.set_issued_at(&SystemTime::now());

    // Per spec Section 8.3.2: exp "MUST be the minimum of the exp value of
    // the Trust Chain from which the resolve response was derived, as well as
    // any Trust Mark included in the response."
    let fallback_exp = SystemTime::now() + Duration::from_secs(86400);
    let chain_exp_iter = result.iter().filter_map(|v| v.payload.expires_at());
    let trust_mark_exp_iter = trust_marks.as_ref().into_iter().flat_map(|tms| {
        tms.iter().filter_map(|tm| {
            let jwt_str = tm.get("trust_mark")?.as_str()?;
            let (tm_payload, _) = get_unverified_payload_header(jwt_str).ok()?;
            tm_payload.expires_at()
        })
    });
    let min_exp = chain_exp_iter
        .chain(trust_mark_exp_iter)
        .min()
        .unwrap_or(fallback_exp);
    payload.set_expires_at(&min_exp);

    if let Some(metadata_val) = metadata {
        let _ = payload.set_claim("metadata", Some(json!(metadata_val)));
    }
    let trust_chain: Vec<String> = result.iter().map(|x| x.jwt.clone()).collect();
    let _ = payload.set_claim("trust_chain", Some(json!(trust_chain.clone())));

    if let Some(tms) = trust_marks
        && !tms.is_empty()
    {
        let _ = payload.set_claim("trust_marks", Some(json!(tms)));
    }

    // Signing JWT
    let keydata = &*PRIVATE_KEY.clone();
    let key = Jwk::from_bytes(keydata)?;

    // Spec §4.3 — also embed the chain in the JWS header. The payload claim
    // is retained for clients that read the chain from the payload; the
    // header parameter lets recipients short-circuit chain resolution
    // without parsing the payload.
    create_signed_jwt_with_header(
        &payload,
        &key,
        Some("resolve-response+jwt"),
        Some(&trust_chain),
    )
}

/// Verify a trust mark JWT issued by *this* TA.
///
/// Returns `true` only when all of the following hold:
/// 1. SHA256 of the JWT exists in `inmor:tm:alltime` (it was actually issued by us).
/// 2. The JWT signature, `exp`, `nbf`, and `iat` validate against the TA's public keyset.
/// 3. `inmor:tm:{sub}` HGET for `trust_mark_type` is not `"revoked"`.
///
/// Any error (Redis failure, signature failure, expiry, missing fields) returns `false`.
/// Mirrors the active-status decision in `trust_mark_status` (Section 8.4.1).
async fn verify_ta_issued_trust_mark(
    trust_mark_jwt: &str,
    ta_public_keyset: &JwkSet,
    conn: &mut redis::aio::ConnectionManager,
) -> bool {
    // 1. Was this mark ever issued by us?
    let mut hasher = Sha256::new();
    hasher.update(trust_mark_jwt.as_bytes());
    let hash = format!("{:x}", hasher.finalize());
    match redis::Cmd::sismember("inmor:tm:alltime", &hash)
        .query_async::<bool>(conn)
        .await
    {
        Ok(true) => {}
        Ok(false) => {
            warn!("trust mark not in inmor:tm:alltime; hash={hash}");
            return false;
        }
        Err(e) => {
            warn!("redis SISMEMBER failed for {hash}: {e}");
            return false;
        }
    }

    // 2. Signature, exp, nbf, iat — all enforced by verify_jwt_with_jwks.
    let (payload, _header) =
        match verify_jwt_with_jwks(trust_mark_jwt, Some(ta_public_keyset.clone())) {
            Ok(p) => p,
            Err(e) => {
                warn!("trust mark signature/temporal verification failed (hash={hash}): {e}");
                return false;
            }
        };

    // 3. Revocation lookup.
    let sub = payload.subject().unwrap_or("");
    let trust_mark_type = payload
        .claim("trust_mark_type")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if validate_redis_key_input(sub).is_err() || validate_redis_key_input(trust_mark_type).is_err()
    {
        warn!("trust mark sub or trust_mark_type fails Redis key validation; hash={hash}");
        return false;
    }
    let hkey = format!("inmor:tm:{sub}");
    match redis::Cmd::hget(hkey, trust_mark_type)
        .query_async::<String>(conn)
        .await
    {
        Ok(mark) => mark != "revoked",
        Err(e) => {
            warn!("redis HGET inmor:tm:{sub} {trust_mark_type} failed: {e}");
            false
        }
    }
}

/// Cached per-issuer data resolved during one /resolve invocation.
#[derive(Clone)]
struct IssuerInfo {
    jwks: JwkSet,
    status_endpoint: String,
}

/// Memoizes external-issuer lookups for the duration of a single /resolve call.
///
/// A subject can carry several marks from the same issuer; without this each
/// would refetch the issuer's entity configuration (and possibly its
/// `jwks_uri`) — burning the 30s trust-mark wall-clock budget on duplicate
/// work. `None` caches a prior failure so we don't retry within the request.
type IssuerInfoCache = HashMap<String, Option<IssuerInfo>>;

/// Fetch + verify an external issuer's entity configuration, returning the data
/// needed to call its trust-mark-status endpoint.
///
/// Returns `None` (and logs at WARN) on any failure: fetch error, parse error,
/// JWKS resolution failure, signature failure, or missing status endpoint.
async fn resolve_external_issuer(
    issuer: &str,
    conn: &mut redis::aio::ConnectionManager,
) -> Option<IssuerInfo> {
    // 1. Fetch the issuer's entity configuration over the SSRF-safe path.
    let ec_jwt = match get_entity_configruation_as_jwt(issuer).await {
        Ok(s) => s,
        Err(e) => {
            warn!("trust mark: failed to fetch entity configuration for issuer {issuer}: {e}");
            return None;
        }
    };

    // 2. Resolve the issuer's JWKS (inline `jwks` claim or, when only the
    //    `jwks_uri` claim is present, fetch and cache via Redis). We need the
    //    unverified payload here just to read those claims; the actual
    //    signature check happens in step 3 once we have the JWKS.
    let (ec_payload_unverified, _) = match get_unverified_payload_header(&ec_jwt) {
        Ok(p) => p,
        Err(e) => {
            warn!("trust mark: failed to parse entity configuration for issuer {issuer}: {e}");
            return None;
        }
    };
    let issuer_jwks = match get_jwks_from_payload_or_uri(&ec_payload_unverified, conn).await {
        Ok(j) => j,
        Err(e) => {
            warn!("trust mark: failed to obtain JWKS for issuer {issuer}: {e}");
            return None;
        }
    };

    // 3. Verify the entity configuration signature against the resolved JWKS
    //    (also enforces exp/nbf/iat temporal claims).
    let (ec_payload, _) = match verify_jwt_with_jwks(&ec_jwt, Some(issuer_jwks.clone())) {
        Ok(p) => p,
        Err(e) => {
            warn!(
                "trust mark: entity configuration signature/temporal verification failed for issuer {issuer}: {e}"
            );
            return None;
        }
    };

    // 4. Find the issuer's trust mark status endpoint.
    let status_endpoint = match ec_payload
        .claim("metadata")
        .and_then(|m| m.get("federation_entity"))
        .and_then(|fe| fe.get("federation_trust_mark_status_endpoint"))
        .and_then(|e| e.as_str())
    {
        Some(s) => s.to_string(),
        None => {
            warn!(
                "trust mark: issuer {issuer} does not advertise federation_trust_mark_status_endpoint; skipping"
            );
            return None;
        }
    };

    Some(IssuerInfo {
        jwks: issuer_jwks,
        status_endpoint,
    })
}

/// Verify a single trust mark from a subject's entity configuration.
///
/// If the mark was issued by this TA (`issuer == ta_entity_id`), this delegates to
/// `verify_ta_issued_trust_mark` (local Redis + signature). Otherwise it:
///
/// 1. Resolves the issuer's JWKS + status endpoint (memoized in `issuer_cache`).
/// 2. Verifies the trust-mark JWT itself (signature + exp/nbf/iat) against the
///    issuer's JWKS. Without this step the resolve-response `exp` calculation
///    would fold in an attacker-controlled `exp` claim from an unverified JWT,
///    and a malformed mark whose status endpoint happens to misbehave could
///    still slip through.
/// 3. POSTs the mark to the issuer's `federation_trust_mark_status_endpoint`
///    (spec §8.4.1) and accepts the mark only if the response JWT verifies
///    against the same JWKS, its `trust_mark` claim echoes back the posted JWT,
///    its `iss` matches the queried issuer, and `status == "active"`.
///
/// Fail-closed at every step: any network error, parse error, signature failure,
/// missing endpoint, or non-active status returns `false` and logs at WARN.
async fn verify_single_trust_mark(
    trust_mark_jwt: &str,
    issuer: &str,
    ta_entity_id: &str,
    ta_public_keyset: &JwkSet,
    conn: &mut redis::aio::ConnectionManager,
    issuer_cache: &mut IssuerInfoCache,
) -> bool {
    if issuer == ta_entity_id {
        return verify_ta_issued_trust_mark(trust_mark_jwt, ta_public_keyset, conn).await;
    }

    // 1. Resolve the issuer's JWKS + status endpoint, caching per /resolve.
    let issuer_info = if let Some(cached) = issuer_cache.get(issuer) {
        match cached {
            Some(info) => info.clone(),
            None => return false, // cached failure
        }
    } else {
        let resolved = resolve_external_issuer(issuer, conn).await;
        issuer_cache.insert(issuer.to_string(), resolved.clone());
        match resolved {
            Some(info) => info,
            None => return false,
        }
    };

    // 2. Verify the trust mark JWT itself against the issuer's JWKS. This
    //    enforces signature + exp/nbf/iat *before* the network round-trip and
    //    before its `exp` is folded into the resolve-response `exp`.
    if let Err(e) = verify_jwt_with_jwks(trust_mark_jwt, Some(issuer_info.jwks.clone())) {
        warn!(
            "trust mark: JWT signature/temporal verification failed against issuer {issuer} JWKS: {e}"
        );
        return false;
    }

    // 3. POST the trust mark to the status endpoint.
    let response_jwt = match post_form_query(
        &issuer_info.status_endpoint,
        &[("trust_mark", trust_mark_jwt)],
    )
    .await
    {
        Ok(s) => s,
        Err(e) => {
            warn!(
                "trust mark: POST {} failed: {e}",
                issuer_info.status_endpoint
            );
            return false;
        }
    };

    // 4. Verify signature and temporal claims of the status response.
    let (status_payload, _) = match verify_jwt_with_jwks(&response_jwt, Some(issuer_info.jwks)) {
        Ok(p) => p,
        Err(e) => {
            warn!(
                "trust mark: status response from {issuer} failed signature/temporal verification: {e}"
            );
            return false;
        }
    };

    // 5. Defense-in-depth: bind the status response to the request and the
    //    queried issuer. Without these, a buggy or compromised issuer could
    //    return a cached "active" response for a *different* mark, or a JWT
    //    whose `iss` doesn't match the issuer whose keys we just trusted.
    let echoed_trust_mark = status_payload
        .claim("trust_mark")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if echoed_trust_mark != trust_mark_jwt {
        warn!(
            "trust mark: status response from {issuer} echoed a different `trust_mark` claim; skipping"
        );
        return false;
    }
    if status_payload.issuer() != Some(issuer) {
        warn!(
            "trust mark: status response `iss` ({:?}) does not match queried issuer {issuer}; skipping",
            status_payload.issuer()
        );
        return false;
    }

    // 6. Inspect the `status` claim. Anything other than "active" → skip.
    let status = status_payload
        .claim("status")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if status != "active" {
        warn!("trust mark: issuer {issuer} reported status='{status}'; skipping");
        return false;
    }

    true
}

/// Verify every trust mark on a subject and return the subset that the federation
/// recognises and which are currently active.
///
/// Reads the TA's own entity configuration from Redis (`inmor:entity_id`) to get
/// the `trust_mark_issuers` claim — the federation-wide trusted issuer list (per
/// spec §3.1.2). For each entry in the subject's `trust_marks` array:
///
/// * Skip if the mark's `trust_mark_type` is not a key in `trust_mark_issuers`.
/// * If the allowed-issuer list for that type is empty, any issuer is acceptable
///   (per spec §3.1.2: "anyone MAY issue Trust Marks with that identifier").
/// * Otherwise, the unverified `iss` from the trust mark JWT must appear in the
///   list.
/// * Finally, `verify_single_trust_mark` must report `true`.
///
/// The original `{trust_mark, trust_mark_type}` objects are returned unchanged so
/// they can be embedded verbatim in the resolve response (per spec §8.3.2).
async fn verify_trust_marks_for_resolve(
    subject_payload: &JwtPayload,
    ta_entity_id: &str,
    ta_public_keyset: &JwkSet,
    conn: &mut redis::aio::ConnectionManager,
) -> Vec<Value> {
    // 1. Subject's trust marks.
    let trust_marks = match subject_payload
        .claim("trust_marks")
        .and_then(|v| v.as_array())
    {
        Some(arr) if !arr.is_empty() => arr.clone(),
        _ => return Vec::new(),
    };
    // The resolved subject's own entity_id — used to drop marks that were
    // issued to a *different* entity (spec §7.4: the trust mark's `sub` claim
    // is the entity the mark is issued to). Without this, an entity could
    // republish another's mark in its own `trust_marks` array and have it
    // accepted as its own.
    let resolve_sub = subject_payload.subject().unwrap_or("");

    // 2. TA's own entity configuration → trust_mark_issuers map.
    let ta_ec_jwt: String = match redis::Cmd::get("inmor:entity_id")
        .query_async::<String>(conn)
        .await
    {
        Ok(s) => s,
        Err(e) => {
            warn!("trust mark resolve: failed to GET inmor:entity_id from Redis: {e}");
            return Vec::new();
        }
    };
    // We trust Redis here — it's our own data written by the admin process.
    // Skipping the signature check is intentional: it avoids a needless self-verify
    // on every resolve and matches the trust boundary used by other endpoints that
    // read `inmor:entity_id`.
    let (ta_payload, _) = match get_unverified_payload_header(&ta_ec_jwt) {
        Ok(p) => p,
        Err(e) => {
            warn!("trust mark resolve: failed to parse TA entity configuration: {e}");
            return Vec::new();
        }
    };
    let trust_mark_issuers = match ta_payload
        .claim("trust_mark_issuers")
        .and_then(|v| v.as_object())
    {
        Some(obj) => obj.clone(),
        None => {
            // No `trust_mark_issuers` claim → no recognised types in this federation.
            return Vec::new();
        }
    };

    // 3. Filter and verify each mark.
    //
    // Hard cap: bounds the per-request HTTP fan-out (each external mark may
    // trigger two outbound calls). See MAX_TRUST_MARKS_PER_RESOLVE.
    if trust_marks.len() > MAX_TRUST_MARKS_PER_RESOLVE {
        warn!(
            "subject has {} trust marks; processing only the first {}",
            trust_marks.len(),
            MAX_TRUST_MARKS_PER_RESOLVE
        );
    }

    let mut verified: Vec<Value> = Vec::new();
    // Per-resolve memoization for external issuers. A subject can carry several
    // marks from the same issuer; without this we'd refetch the issuer EC (and
    // potentially its `jwks_uri`) once per mark and burn the 30s budget.
    let mut issuer_cache: IssuerInfoCache = HashMap::new();
    for tm in trust_marks.iter().take(MAX_TRUST_MARKS_PER_RESOLVE) {
        let tm_obj = match tm.as_object() {
            Some(o) => o,
            None => continue,
        };
        let jwt_str = match tm_obj.get("trust_mark").and_then(|v| v.as_str()) {
            Some(s) => s,
            None => continue,
        };
        let tm_type = match tm_obj.get("trust_mark_type").and_then(|v| v.as_str()) {
            Some(s) => s,
            None => continue,
        };

        let allowed = match trust_mark_issuers.get(tm_type).and_then(|v| v.as_array()) {
            Some(a) => a,
            None => continue, // type not recognised by federation
        };

        let (unverified_payload, _) = match get_unverified_payload_header(jwt_str) {
            Ok(p) => p,
            Err(e) => {
                warn!("trust mark resolve: failed to parse trust mark JWT: {e}");
                continue;
            }
        };

        // Spec §7.4: the outer `trust_mark_type` MUST equal the JWT's inner
        // `trust_mark_type` claim. Drop the mark on mismatch to avoid emitting
        // a self-contradictory entry in the resolve response. Comparing the
        // unverified inner claim is safe — the inner bytes are part of the
        // signed payload, so any divergence between this value and what
        // `verify_single_trust_mark` would later see is impossible.
        let inner_tm_type = unverified_payload
            .claim("trust_mark_type")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if inner_tm_type != tm_type {
            warn!(
                "trust mark resolve: outer trust_mark_type {tm_type} != inner {inner_tm_type} (spec §7.4); skipping"
            );
            continue;
        }

        // Spec §7.4: the trust mark's `sub` is the entity to which the mark
        // is issued. A mark whose inner `sub` doesn't match the entity we're
        // resolving belongs to someone else and must not appear here.
        let mark_sub = unverified_payload.subject().unwrap_or("");
        if mark_sub != resolve_sub {
            warn!(
                "trust mark resolve: trust mark sub {mark_sub} != resolved subject {resolve_sub}; skipping"
            );
            continue;
        }

        let issuer = unverified_payload.issuer().unwrap_or("").to_string();
        if issuer.is_empty() {
            warn!("trust mark resolve: trust mark JWT has empty `iss`");
            continue;
        }

        // Empty allowed list = any issuer (per spec §3.1.2).
        if !allowed.is_empty() {
            let issuer_ok = allowed.iter().any(|v| v.as_str() == Some(issuer.as_str()));
            if !issuer_ok {
                warn!(
                    "trust mark resolve: issuer {issuer} not in allowed list for type {tm_type}; skipping"
                );
                continue;
            }
        }

        if verify_single_trust_mark(
            jwt_str,
            &issuer,
            ta_entity_id,
            ta_public_keyset,
            conn,
            &mut issuer_cache,
        )
        .await
        {
            verified.push(tm.clone());
        }
    }

    verified
}

/// https://openid.net/specs/openid-federation-1_0.html#name-resolve-request
#[get("/resolve")]
pub async fn resolve_entity(
    info: Query<ResolveParams>,
    redis: web::Data<redis::Client>,
    state: web::Data<AppState>,
) -> actix_web::Result<HttpResponse> {
    let mut found_ta = false;
    let ResolveParams {
        sub,
        trust_anchors,
        entity_type,
    } = info.into_inner();
    let tas: Vec<&str> = trust_anchors.iter().map(|s| s as &str).collect();
    let mut visisted: HashSet<String> = HashSet::new();
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;
    // Now loop over the trust_anchors
    let result =
        match resolve_entity_to_trustanchor(&sub, tas, true, &mut visisted, 0, &mut conn, None)
            .await
        {
            Ok(res) => res,
            Err(e) => {
                warn!("Error resolving entity {} to trust anchors: {}", sub, e);
                // Spec §10.5 — a transient fetch failure surfaces as
                // HTTP 503 + `Retry-After` so the client can back off and
                // retry. Permanent failures keep the existing 400
                // `invalid_trust_chain` shape.
                if let Some(fe) = e.downcast_ref::<FetchError>()
                    && fe.transient
                {
                    let retry_after = fe.retry_after_seconds.unwrap_or(DEFAULT_RETRY_AFTER_SECS);
                    return Ok(HttpResponse::ServiceUnavailable()
                        .insert_header(("Retry-After", retry_after.to_string()))
                        .json(json!({
                            "error": "temporarily_unavailable",
                            "error_description": fe.message,
                        })));
                }
                // Surface the underlying error message. The early walker
                // returns from this branch are dominated by leaf EC
                // self-verification failures (bad signature, missing
                // jwks, unknown critical claim per §3.1.1, iss != sub)
                // -- exactly the cases where a precise reason helps the
                // operator diagnose a federation misconfiguration. The
                // messages come from internal verifier code, not user
                // input, so echoing them is safe.
                return error_response_400(
                    "invalid_trust_chain",
                    &format!("Failed to find trust chain: {e}"),
                );
            }
        };

    // Verify that the result is not empty and we actually found a TA
    if result.is_empty() {
        warn!("Empty trust chain result for entity: {}", sub);
        return error_response_400("invalid_trust_chain", "Failed to find trust chain");
    }
    if result.iter().any(|i| i.taresult) {
        // Means we found our trust anchor
        // FOUND_TA: Here if verify if we actually found any of the TA we wanted.
        found_ta = true;
    }
    if !found_ta {
        warn!("No trust anchor found in chain for entity: {}", sub);
        return error_response_400("invalid_trust_chain", "Failed to find trust chain");
    }

    // Per spec §8.3: "The resolver MUST verify that all present Trust Marks with
    // identifiers recognized within the Federation are active. The response set
    // MUST include only verified Trust Marks." `result[0]` is the subject's own
    // entity configuration (the chain runs subject → ... → TA).
    //
    // The whole phase runs under a wall-clock budget — combined with
    // MAX_TRUST_MARKS_PER_RESOLVE, this bounds the worst-case worker-thread
    // time a malicious subject EC can cause.
    let verified_trust_marks = match tokio::time::timeout(
        Duration::from_secs(TRUST_MARK_VERIFICATION_BUDGET_SECS),
        verify_trust_marks_for_resolve(
            &result[0].payload,
            &state.entity_id,
            &state.public_keyset,
            &mut conn,
        ),
    )
    .await
    {
        Ok(marks) => marks,
        Err(_) => {
            warn!(
                "trust mark verification exceeded {TRUST_MARK_VERIFICATION_BUDGET_SECS}s budget for sub={sub}; returning none"
            );
            Vec::new()
        }
    };
    let trust_marks = if verified_trust_marks.is_empty() {
        None
    } else {
        Some(verified_trust_marks)
    };

    let mut mpolicy: Option<Map<String, Value>> = None;
    let reversed: Vec<&VerifiedJWT> = result.iter().rev().collect();

    // We need to skip the top one (the trust anchor's entity configuration)
    for (i, res) in reversed.iter().enumerate().skip(1) {
        println!("\n{:?}\n", res.payload);
        mpolicy = match mpolicy {
            // This is when we have some policy the higher subordinate statement
            Some(val) => {
                // But we should only apply claim from subordinate statements
                if res.substatement {
                    let new_policy = res.payload.claim("metadata_policy");
                    match new_policy {
                        Some(p) => {
                            let temp_val = json!(val);
                            let merged = merge_policies(&temp_val, p);
                            match merged {
                                Ok(policy) => Some(policy),
                                Err(e) => {
                                    // Spec §6.1.3.2: surface the crate's error
                                    // (often the offending critical operator
                                    // name) rather than swallow it.
                                    warn!("metadata_policy merge failed: {e}");
                                    return error_response_400(
                                        "invalid_trust_chain",
                                        &format!("metadata policy merge failed: {e}"),
                                    );
                                }
                            }
                        }
                        None => Some(val),
                    }
                } else {
                    // Means the final entity statement
                    // We should now apply the merged policy at val to the metadata claim
                    let Some(metadata) = res.payload.claim("metadata").cloned() else {
                        return error_response_400(
                            "invalid_trust_chain",
                            "missing metadata in entity statement",
                        );
                    };
                    debug!("Final policy checking: val={val:?} metadata={metadata:?}");
                    let mut forced_metadata: Option<&Value> = None;
                    // Let us see if we have any subordinate statement's metadata to apply first
                    if i > 0 {
                        let last_sub_statement = reversed[i - 1];
                        forced_metadata = last_sub_statement.payload.claim("metadata");
                    }
                    let Some(metadata_obj) = metadata.as_object() else {
                        return error_response_400(
                            "invalid_trust_chain",
                            "metadata is not an object",
                        );
                    };
                    let full_policy = match forced_metadata {
                        Some(fm) => json!({"metadata_policy": val.clone(), "metadata": fm.clone()}),
                        None => json!({"metadata_policy": val.clone()}),
                    };
                    let Some(full_policy_document) = full_policy.as_object() else {
                        return error_response_400(
                            "invalid_trust_chain",
                            "failed to create policy document",
                        );
                    };
                    // Here the policy contains for every kind of entity.
                    // In the full_policy_document we have any forced metadata from the authority.
                    match apply_policy_document_on_metadata(full_policy_document, metadata_obj) {
                        Ok(applied) => {
                            debug!("Applied final metadata after applying policy: {applied:?}");
                            Some(applied)
                        }
                        Err(e) => {
                            // Spec §3.1.3 / §6.1.3.2: surface the crate's
                            // error (e.g., unknown critical operator) instead
                            // of a generic message.
                            warn!("metadata_policy apply failed: {e}");
                            return error_response_400(
                                "invalid_trust_chain",
                                &format!("metadata policy apply failed: {e}"),
                            );
                        }
                    }
                }
            }

            // Means first time getting a metadata policy.
            // We should store it properly in mpolicy
            None => {
                // We should only get it from a subordinate statement
                if res.substatement {
                    let new_policy = res.payload.claim("metadata_policy");
                    match new_policy {
                        Some(p) => {
                            if let Some(data) = p.as_object() {
                                Some(data.clone())
                            } else {
                                Some(Map::new())
                            }
                        }

                        // Even the subordinate statement does not have any policy
                        None => Some(Map::new()),
                    }
                } else {
                    // Not a subordinate statement
                    // Means an entity statement
                    // Means no policy and only statement, nothing to verify against
                    // Return the original metadata here
                    //None
                    //Some(Map::new())
                    res.payload
                        .claim("metadata")
                        .and_then(|m| m.as_object())
                        .cloned()
                }
            }
        };
    }
    // HACK:
    debug!("After the whole call: {mpolicy:?}");
    // The mpolicy now contains the final metadata after applying policies.

    // Apply entity_type filtering if provided
    // Per OpenID Federation spec, entity_type filters which metadata keys are returned.
    // If entity_type is provided but none of the types match, return all metadata.
    let filtered_metadata = filter_metadata_by_entity_types(mpolicy, entity_type.as_ref());

    // If we reach here means we have a list of JWTs and also verified metadata.
    let resp = create_resolve_response_jwt(&state, &sub, &result, filtered_metadata, trust_marks)
        .map_err(error::ErrorInternalServerError)?;
    Ok(HttpResponse::Ok()
        .insert_header(("content-type", "application/resolve-response+jwt"))
        .body(resp))
}

/// Filters metadata by entity_type.
/// If entity_types is None or empty, returns the original metadata.
/// If entity_types is provided, returns only the metadata keys that match.
/// If no matching types found in metadata, returns the original metadata (per spec).
fn filter_metadata_by_entity_types(
    metadata: Option<Map<String, Value>>,
    entity_types: Option<&Vec<String>>,
) -> Option<Map<String, Value>> {
    let meta = metadata?;

    let Some(types) = entity_types else {
        return Some(meta);
    };

    if types.is_empty() {
        return Some(meta);
    }

    let mut filtered = Map::new();
    for entity_type in types {
        if let Some(value) = meta.get(entity_type) {
            filtered.insert(entity_type.clone(), value.clone());
        }
    }

    // If no matching types found, return all metadata
    if filtered.is_empty() {
        return Some(meta);
    }

    Some(filtered)
}

/// To create the signed JWT for trust mark status response
/// Per spec Section 8.4.2, the response includes `trust_mark` (the full JWT) and `status`.
fn create_trustmark_status_response_jwt(
    state: &web::Data<AppState>,
    trust_mark: &str,
    status: &str,
) -> Result<String, JoseError> {
    let mut payload = JwtPayload::new();
    let iss = state.entity_id.clone();
    payload.set_issuer(iss);
    payload.set_issued_at(&SystemTime::now());

    // Set expiry after 24 hours
    let exp = SystemTime::now() + Duration::from_secs(86400);
    payload.set_expires_at(&exp);
    payload.set_claim("trust_mark", Some(json!(trust_mark)))?;
    payload.set_claim("status", Some(json!(status)))?;

    // Signing JWT
    let keydata = &*PRIVATE_KEY.clone();
    let key = Jwk::from_bytes(keydata)?;

    create_signed_jwt(&payload, &key, Some("trust-mark-status-response+jwt"))
}

/// https://openid.net/specs/openid-federation-1_0.html#section-8.4.1
///
/// Per spec §8.4.1, requests use `application/x-www-form-urlencoded`. Actix's
/// `web::Form` extractor enforces this for us: a request with the wrong
/// Content-Type fails extraction with `UrlencodedError::ContentType`, which
/// actix renders as `415 Unsupported Media Type` before the handler runs.
#[post("/trust_mark_status")]
pub async fn trust_mark_status(
    info: web::Form<TrustMarkStatusParams>,
    redis: web::Data<redis::Client>,
    state: web::Data<AppState>,
) -> actix_web::Result<HttpResponse> {
    let TrustMarkStatusParams { trust_mark } = info.into_inner();
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    // Create sha256sum of the trust_mark and see if it exists in `inmor:tm:alltime` set.
    let mut hasher = Sha256::new();
    hasher.update(trust_mark.as_bytes());
    let trust_mark_hash = format!("{:x}", hasher.finalize());

    let exists: bool = redis::Cmd::sismember("inmor:tm:alltime", &trust_mark_hash)
        .query_async::<bool>(&mut conn)
        .await
        .map_err(error::ErrorInternalServerError)?;

    if !exists {
        debug!("Trust mark not found in Redis: hash={}", trust_mark_hash);
        return error_response_404("not_found", "Trust mark not found.");
    }

    // Verify the signature first (no temporal validation yet). This is the
    // gate that distinguishes "invalid" from "expired": if the signature
    // doesn't check out — wrong key, malformed signature, unknown algorithm —
    // we MUST classify as "invalid" regardless of what the `exp` claim says.
    // Only marks with a valid signature whose `exp` is in the past should be
    // reported as "expired". The previous implementation read `exp` from the
    // unverified payload and classified expired *before* checking the
    // signature, which let an attacker forge an "expired" classification by
    // submitting a JWT with any `exp` and a bad signature.
    let jwks = state.public_keyset.clone();
    let status = match verify_jwt_signature_with_jwks(&trust_mark, Some(jwks)) {
        Err(_) => "invalid",
        // Spec §3.1.1 — an unknown critical claim makes the mark
        // unprocessable. Classify it as "invalid" alongside bad-signature
        // failures rather than letting it through to the active/expired
        // logic. The `crit` check is a structural check and intentionally
        // does not interfere with the active-vs-expired distinction:
        // a signed-but-expired mark with a clean `crit` is still
        // classified as "expired".
        Ok((payload, _)) if enforce_crit_claim(&payload).is_err() => "invalid",
        Ok((payload, _)) => {
            let expired = payload
                .expires_at()
                .map(|exp| exp <= SystemTime::now())
                .unwrap_or(false);
            if expired {
                "expired"
            } else {
                let v = json!("");
                let sub = payload.subject().unwrap_or("");
                let claims = payload.claims_set();
                let trustmarktype = claims
                    .get("trust_mark_type")
                    .unwrap_or(&v)
                    .as_str()
                    .unwrap_or("");

                if let Err(e) = validate_redis_key_input(sub) {
                    return error_response_400(
                        "invalid_request",
                        &format!("invalid sub in JWT: {e}"),
                    );
                }
                if let Err(e) = validate_redis_key_input(trustmarktype) {
                    return error_response_400(
                        "invalid_request",
                        &format!("invalid trust_mark_type in JWT: {e}"),
                    );
                }

                let hkey = format!("inmor:tm:{sub}");
                let mark = redis::Cmd::hget(hkey, trustmarktype)
                    .query_async::<String>(&mut conn)
                    .await
                    .map_err(error::ErrorInternalServerError)?;

                if mark != "revoked" {
                    "active"
                } else {
                    "revoked"
                }
            }
        }
    };

    let resp = match create_trustmark_status_response_jwt(&state, &trust_mark, status) {
        Ok(r) => r,
        Err(err) => {
            // Log here about the failure
            return Err(error::ErrorInternalServerError(err));
        }
    };

    Ok(HttpResponse::Ok()
        .insert_header(("content-type", "application/trust-mark-status-response+jwt"))
        .body(resp))
}

/// https://openid.net/specs/openid-federation-1_0.html#section-8.7.1
/// Federation Historical Keys endpoint
/// Returns a signed JWK Set JWT containing historical keys that have an `exp` field.
/// Returns 404 if no historical keys are found.
#[get("/historical_keys")]
pub async fn federation_historical_keys(
    redis: web::Data<redis::Client>,
) -> actix_web::Result<HttpResponse> {
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let res: Option<String> = redis::Cmd::get("inmor:historical_keys")
        .query_async(&mut conn)
        .await
        .map_err(error::ErrorInternalServerError)?;

    match res {
        Some(token) => Ok(HttpResponse::Ok()
            .insert_header(("content-type", "application/jwk-set+jwt"))
            .body(token)),
        None => error_response_404("not_found", "no historical keys found"),
    }
}

/// https://openid.net/specs/openid-federation-1_0.html#section-8.5.1
#[get("/trust_mark_list")]
pub async fn trust_mark_list(
    info: Query<TrustMarkListParams>,
    redis: web::Data<redis::Client>,
    _state: web::Data<AppState>,
) -> actix_web::Result<HttpResponse> {
    let TrustMarkListParams {
        trust_mark_type,
        sub,
    } = info.into_inner();

    if let Err(e) = validate_redis_key_input(&trust_mark_type) {
        return error_response_400("invalid_request", &format!("invalid trust_mark_type: {e}"));
    }

    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let query = format!("inmor:tmtype:{trust_mark_type}");

    let res = redis::Cmd::smembers(query)
        .query_async::<Vec<String>>(&mut conn)
        .await
        .map_err(error::ErrorInternalServerError);
    match res {
        Ok(mut result) => {
            if let Some(sub_entity) = sub {
                // Per spec Section 8.5.1: filter to only the Entity matching sub
                if result.contains(&sub_entity) {
                    result = vec![sub_entity];
                } else {
                    // Filtering to nothing = empty array
                    result = vec![];
                }
            }

            let body = match serde_json::to_string(&result) {
                Ok(d) => d,
                Err(_) => return Err(error::ErrorInternalServerError("JSON error")),
            };
            Ok(HttpResponse::Ok()
                .insert_header(("content-type", "application/json"))
                .body(body))
        }
        Err(_) => error_response_404("not_found", "Trust mark type not found."),
    }
}

///
/// https://openid.net/specs/openid-federation-1_0.html#section-8.6.1
#[get("/trust_mark")]
pub async fn trust_mark_query(
    info: Query<TrustMarkParams>,
    redis: web::Data<redis::Client>,
    _state: web::Data<AppState>,
) -> actix_web::Result<HttpResponse> {
    let TrustMarkParams {
        trust_mark_type,
        sub,
    } = info.into_inner();

    if let Err(e) = validate_redis_key_input(&sub) {
        return error_response_400("invalid_request", &format!("invalid sub: {e}"));
    }
    if let Err(e) = validate_redis_key_input(&trust_mark_type) {
        return error_response_400("invalid_request", &format!("invalid trust_mark_type: {e}"));
    }

    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let query = format!("inmor:tm:{sub}");

    let res = redis::Cmd::hget(query, &trust_mark_type)
        .query_async::<String>(&mut conn)
        .await
        .map_err(error::ErrorInternalServerError);
    match res {
        Ok(result) => Ok(HttpResponse::Ok()
            .insert_header(("content-type", "application/trust-mark+jwt"))
            .body(result)),
        Err(e) => {
            debug!(
                "Trust mark not found for sub={}, type={}: {:?}",
                sub, trust_mark_type, e
            );
            error_response_404("not_found", "Trust mark not found.")
        }
    }
}

/// Fetches the subordinate statement from authority
pub async fn fetch_subordinate_statement(fetch_url: &str, entity_id: &str) -> Result<String> {
    let url = format!("{fetch_url}?sub={entity_id}");
    debug!("FETCH {url}");
    return get_query(&url).await;
}

/// Get the entity configuration for a given entity_id
pub async fn get_entity_configruation_as_jwt(entity_id: &str) -> Result<String> {
    let url = format!("{entity_id}/{WELL_KNOWN}");
    debug!("EC {url}");
    return get_query(&url).await;
}

/// Returns true if the IP address is in a private, loopback, or link-local range.
fn is_private_ip(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            v4.is_loopback()       // 127.0.0.0/8
            || v4.is_private()     // 10/8, 172.16/12, 192.168/16
            || v4.is_link_local()  // 169.254/16
            || v4.is_unspecified() // 0.0.0.0
            || v4.is_broadcast() // 255.255.255.255
        }
        IpAddr::V6(v6) => {
            v6.is_loopback()       // ::1
            || v6.is_unspecified() // ::
            // unique local (fc00::/7) and link-local (fe80::/10)
            || (v6.segments()[0] & 0xfe00) == 0xfc00
            || (v6.segments()[0] & 0xffc0) == 0xfe80
        }
    }
}

/// Known OpenID Federation entity types accepted in query parameters.
const KNOWN_ENTITY_TYPES: &[&str] = &[
    "openid_provider",
    "openid_relying_party",
    "federation_entity",
    "oauth_authorization_server",
    "oauth_client",
    "oauth_resource",
];

/// Validates that a user-supplied string is safe to use in a Redis key.
/// Rejects control characters (including newlines and null bytes) and
/// enforces a maximum length to prevent memory abuse.
fn validate_redis_key_input(input: &str) -> Result<(), &'static str> {
    const MAX_KEY_INPUT_LEN: usize = 2048;
    if input.is_empty() {
        return Err("empty value");
    }
    if input.len() > MAX_KEY_INPUT_LEN {
        return Err("value too long");
    }
    if input.chars().any(|c| c.is_control()) {
        return Err("value contains control characters");
    }
    Ok(())
}

/// Validates that a string is a known OpenID Federation entity type.
fn validate_entity_type(etype: &str) -> Result<(), &'static str> {
    if KNOWN_ENTITY_TYPES.contains(&etype) {
        Ok(())
    } else {
        Err("unknown entity type")
    }
}

/// Validates a URL for federation use: HTTPS scheme, no private IPs.
/// When `allow_http` is true (development mode), all checks are relaxed.
/// SSRF gate + scheme allowlist for outbound federation URLs.
///
/// Failures are classified as `FetchError`:
/// * URL parse / scheme block / no host / private-IP block are *permanent*
///   — no amount of retrying changes the answer, and propagating them as
///   transient would let callers burn retries on a policy denial.
/// * DNS resolution failure (incl. empty resolution) is *transient* — a
///   resolver hiccup is exactly the kind of thing §10.5 says to retry.
async fn validate_federation_url(url_str: &str, allow_http: bool) -> Result<()> {
    let parsed = url::Url::parse(url_str).map_err(|e| {
        anyhow::Error::new(FetchError::permanent(format!(
            "Invalid URL '{url_str}': {e}"
        )))
    })?;

    // 1. Scheme check
    match parsed.scheme() {
        "https" => {}
        "http" if allow_http => {}
        scheme => {
            return Err(anyhow::Error::new(FetchError::permanent(format!(
                "Blocked scheme '{scheme}' in URL '{url_str}' — only HTTPS allowed"
            ))));
        }
    }

    // In development mode, skip DNS/IP validation
    if allow_http {
        return Ok(());
    }

    // 2. Must have a host
    let host = parsed.host_str().ok_or_else(|| {
        anyhow::Error::new(FetchError::permanent(format!(
            "URL '{url_str}' has no host"
        )))
    })?;

    // 3. Resolve DNS and check all IPs
    let port = parsed.port_or_known_default().unwrap_or(443);
    let addr = format!("{}:{}", host, port);
    let resolved: Vec<std::net::SocketAddr> = tokio::net::lookup_host(&addr)
        .await
        .map_err(|e| {
            // DNS failures (incl. SERVFAIL, timeout, no nameservers) are
            // transient per §10.5.
            anyhow::Error::new(FetchError::transient(
                None,
                format!("DNS resolution failed for '{host}': {e}"),
            ))
        })?
        .collect();

    if resolved.is_empty() {
        return Err(anyhow::Error::new(FetchError::transient(
            None,
            format!("DNS resolution returned no addresses for '{host}'"),
        )));
    }

    for sock_addr in &resolved {
        if is_private_ip(&sock_addr.ip()) {
            return Err(anyhow::Error::new(FetchError::permanent(format!(
                "Blocked request to private/internal IP {} (resolved from '{host}')",
                sock_addr.ip()
            ))));
        }
    }

    Ok(())
}

/// To do a POST with `application/x-www-form-urlencoded` body. Uses the same SSRF gate,
/// shared HTTP client (timeouts/redirect limit/pool), and `MAX_RESPONSE_BYTES` cap as
/// `get_query`. Used to call external trust mark issuers' `/trust_mark_status` endpoint.
pub async fn post_form_query(url: &str, form: &[(&str, &str)]) -> Result<String> {
    validate_federation_url(url, ALLOW_HTTP.load(std::sync::atomic::Ordering::Relaxed)).await?;
    let response = HTTP_CLIENT.post(url).form(form).send().await?;
    if !response.status().is_success() {
        bail!("POST to '{}' returned status {}", url, response.status());
    }
    if let Some(len) = response.content_length()
        && len > MAX_RESPONSE_BYTES as u64
    {
        bail!(
            "Response too large ({} bytes) from '{}', max {} bytes",
            len,
            url,
            MAX_RESPONSE_BYTES
        );
    }
    let bytes = response.bytes().await?;
    if bytes.len() > MAX_RESPONSE_BYTES {
        bail!(
            "Response too large ({} bytes) from '{}', max {} bytes",
            bytes.len(),
            url,
            MAX_RESPONSE_BYTES
        );
    }
    String::from_utf8(bytes.to_vec())
        .map_err(|e| anyhow!("Response from '{}' is not valid UTF-8: {}", url, e))
}

/// Sleep duration (ms) for the next retry of `get_query`.
///
/// We honour an upstream `Retry-After` only when it is *shorter* than the
/// next computed local backoff. That way a server can signal "come back
/// sooner" but a malicious or buggy upstream cannot stall us beyond our
/// own retry pacing by returning a very large `Retry-After`. The local
/// backoff is already capped at `FETCH_BACKOFF_CAP_MS`, so the result
/// inherits that bound.
fn compute_retry_sleep_ms(local_backoff_ms: u64, retry_after_seconds: Option<u64>) -> u64 {
    match retry_after_seconds {
        Some(s) => s.saturating_mul(1_000).min(local_backoff_ms),
        None => local_backoff_ms,
    }
}

/// To do a GET query. Uses the shared HTTP client with timeouts and connection limits.
/// Enforces a maximum response body size of `MAX_RESPONSE_BYTES`.
///
/// Per OpenID Federation §10.5, transient failures (HTTP 5xx, 429,
/// connection / DNS / timeout) are retried with exponential backoff up to
/// `FETCH_MAX_RETRIES` times. The server's `Retry-After` header is
/// honoured only when it is shorter than the next computed local backoff
/// (so a large server-supplied value cannot stall us beyond our own
/// retry pacing). After retries are
/// exhausted the error is returned as a `FetchError::transient(...)`
/// wrapped in `anyhow::Error`; permanent failures (4xx other than 429,
/// SSRF denial, body-cap exceeded, malformed body) are returned as
/// `FetchError::permanent(...)`. Callers that care can downcast the
/// returned `anyhow::Error` to `FetchError` to distinguish.
pub async fn get_query(url: &str) -> Result<String> {
    let mut backoff_ms = FETCH_BACKOFF_INITIAL_MS;
    let mut last_transient_msg = String::new();
    let mut last_retry_after: Option<u64> = None;

    for attempt in 0..=FETCH_MAX_RETRIES {
        match try_one_fetch(url).await {
            Ok(body) => return Ok(body),
            Err(e) => {
                let fe = e.downcast_ref::<FetchError>();
                match fe {
                    // Permanent — never retry.
                    Some(f) if !f.transient => return Err(e),
                    // Transient (classified) — capture details, then back off.
                    Some(f) => {
                        last_retry_after = f.retry_after_seconds;
                        last_transient_msg = f.message.clone();
                    }
                    // Untyped — treat as transient and retry. The classifier
                    // is best-effort; if a code path produces an unclassified
                    // error we err on the side of retrying.
                    None => {
                        last_retry_after = None;
                        last_transient_msg = format!("{e}");
                    }
                }
                if attempt >= FETCH_MAX_RETRIES {
                    break;
                }
                let sleep_ms = compute_retry_sleep_ms(backoff_ms, last_retry_after);
                tokio::time::sleep(Duration::from_millis(sleep_ms)).await;
                backoff_ms = (backoff_ms.saturating_mul(2)).min(FETCH_BACKOFF_CAP_MS);
            }
        }
    }

    Err(anyhow::Error::new(FetchError::transient(
        last_retry_after,
        last_transient_msg,
    )))
}

/// One attempt of the get_query pipeline: SSRF gate -> HTTP request ->
/// body drain. Returns a typed `FetchError` (wrapped in `anyhow::Error`)
/// so the retry loop can decide permanent-vs-transient. Body-read failures
/// and DNS hiccups inside the SSRF gate both surface as transient and
/// participate in the retry loop.
async fn try_one_fetch(url: &str) -> Result<String> {
    validate_federation_url(url, ALLOW_HTTP.load(std::sync::atomic::Ordering::Relaxed)).await?;
    let response = HTTP_CLIENT.get(url).send().await.map_err(|e| {
        anyhow::Error::new(FetchError::transient(
            None,
            format!("transport error fetching '{url}': {e}"),
        ))
    })?;
    let status = response.status();
    if status.is_success() {
        return read_response_body(url, response).await;
    }
    if status.as_u16() == 429 || status.is_server_error() {
        let retry_after = response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|v| v.to_str().ok())
            .and_then(|s| s.parse::<u64>().ok());
        return Err(anyhow::Error::new(FetchError::transient(
            retry_after,
            format!("HTTP {status} from '{url}'"),
        )));
    }
    // 4xx other than 429, 3xx that the client still surfaced — permanent.
    Err(anyhow::Error::new(FetchError::permanent(format!(
        "HTTP {status} from '{url}'"
    ))))
}

/// Drain a successful response into a UTF-8 string, enforcing the body cap.
async fn read_response_body(url: &str, response: reqwest::Response) -> Result<String> {
    if let Some(len) = response.content_length()
        && len > MAX_RESPONSE_BYTES as u64
    {
        return Err(anyhow::Error::new(FetchError::permanent(format!(
            "Response too large ({len} bytes) from '{url}', max {MAX_RESPONSE_BYTES} bytes"
        ))));
    }
    let bytes = match response.bytes().await {
        Ok(b) => b,
        Err(e) => {
            return Err(anyhow::Error::new(FetchError::transient(
                None,
                format!("body read failed for '{url}': {e}"),
            )));
        }
    };
    if bytes.len() > MAX_RESPONSE_BYTES {
        return Err(anyhow::Error::new(FetchError::permanent(format!(
            "Response too large ({} bytes) from '{url}', max {MAX_RESPONSE_BYTES} bytes",
            bytes.len()
        ))));
    }
    String::from_utf8(bytes.to_vec()).map_err(|e| {
        anyhow::Error::new(FetchError::permanent(format!(
            "Response from '{url}' is not valid UTF-8: {e}"
        )))
    })
}

/// Lightweight liveness check endpoint.
/// Returns 200 with `{"status": "ok"}` if Redis is reachable,
/// or 503 with `{"status": "error", "detail": "redis unavailable"}` if not.
#[get("/health")]
pub async fn health(redis: web::Data<redis::Client>) -> HttpResponse {
    let conn_result = redis.get_connection_manager().await;
    match conn_result {
        Ok(mut conn) => {
            let ping: Result<String, _> = redis::cmd("PING").query_async(&mut conn).await;
            match ping {
                Ok(_) => HttpResponse::Ok().json(json!({"status": "ok"})),
                Err(_) => HttpResponse::ServiceUnavailable()
                    .json(json!({"status": "error", "detail": "redis unavailable"})),
            }
        }
        Err(_) => HttpResponse::ServiceUnavailable()
            .json(json!({"status": "error", "detail": "redis unavailable"})),
    }
}

/// Detailed operational status endpoint.
/// Returns counts of keys, subordinates, trust marks, and collection data.
#[get("/status")]
pub async fn server_status(
    redis: web::Data<redis::Client>,
    state: web::Data<AppState>,
) -> actix_web::Result<HttpResponse> {
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    // Pipeline Redis queries for efficiency (single round-trip)
    let mut pipe = redis::pipe();
    pipe.cmd("EXISTS")
        .arg("inmor:historical_keys")
        .cmd("HLEN")
        .arg("inmor:subordinates:jwt")
        .cmd("SCARD")
        .arg("inmor:tm:alltime")
        .cmd("HLEN")
        .arg("inmor:collection:entities")
        .cmd("SCARD")
        .arg("inmor:collection:by_type:openid_provider")
        .cmd("SCARD")
        .arg("inmor:collection:by_type:openid_relying_party")
        .cmd("SCARD")
        .arg("inmor:collection:by_type:federation_entity")
        .cmd("GET")
        .arg("inmor:collection:last_updated")
        .cmd("SMEMBERS")
        .arg("inmor:tmtypes");

    let results: (
        bool,        // historical_keys exists
        u64,         // subordinate count
        u64,         // total trust marks
        u64,         // collection entities
        u64,         // OPs
        u64,         // RPs
        u64,         // intermediates
        Option<u64>, // last_updated
        Vec<String>, // trust mark type keys
    ) = pipe
        .query_async(&mut conn)
        .await
        .map_err(error::ErrorInternalServerError)?;

    // Trust mark type URLs from the inmor:tmtypes index set
    let trust_mark_types: Vec<String> = results.8;

    let public_key_count = PUBLIC_KEYS.len();

    let response = json!({
        "entity_id": state.entity_id,
        "version": env!("CARGO_PKG_VERSION"),
        "status": "ok",
        "keys": {
            "public_keys": public_key_count,
            "historical_keys_available": results.0,
        },
        "subordinates": {
            "direct": results.1,
        },
        "trust_marks": {
            "types": trust_mark_types,
            "total_issued": results.2,
        },
        "collection": {
            "total_entities": results.3,
            "openid_providers": results.4,
            "openid_relying_parties": results.5,
            "intermediates": results.6,
            "last_updated": results.7,
        },
    });

    Ok(HttpResponse::Ok().json(response))
}

pub fn error_response_404(edetails: &str, message: &str) -> actix_web::Result<HttpResponse> {
    Ok(HttpResponse::NotFound().json(json!({
        "error": edetails,
        "error_description": message
    })))
}

pub fn error_response_400(edetails: &str, message: &str) -> actix_web::Result<HttpResponse> {
    Ok(HttpResponse::BadRequest().json(json!({
        "error": edetails,
        "error_description": message
    })))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::SystemTime;

    #[test]
    fn test_create_signed_jwt_with_all_key_types() {
        // Load all private keys from the privatekeys directory
        let keys_dir = "./privatekeys";
        let entries = fs::read_dir(keys_dir).expect("Failed to read privatekeys directory");

        let mut keys = Vec::new();
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                let key_data = fs::read(&path).expect("Failed to read key file");
                let key = Jwk::from_bytes(&key_data).expect("Failed to parse JWK");
                keys.push(key);
            }
        }

        assert!(!keys.is_empty(), "No private keys found in ./privatekeys");

        // Test signing with each key type
        for key in keys.iter() {
            let alg = key.algorithm().unwrap_or("RS256");
            let kid = key.key_id().unwrap_or("unknown");

            // Create test payload
            let mut payload = JwtPayload::new();
            payload.set_issuer("http://localhost:8080");
            payload.set_subject("http://example.com");
            payload.set_issued_at(&SystemTime::now());

            let exp = SystemTime::now() + Duration::from_secs(3600);
            payload.set_expires_at(&exp);
            payload
                .set_claim("test_claim", Some(json!("test_value")))
                .expect("Failed to set test claim in test_create_signed_jwt_with_all_key_types");

            // Sign the JWT
            let token_str = create_signed_jwt(&payload, &key, Some("test+jwt"))
                .expect(&format!("Failed to sign with {} (kid: {})", alg, kid));

            // Verify it's a valid JWT format
            assert_eq!(
                token_str.matches('.').count(),
                2,
                "Invalid JWT format for key {} ({})",
                alg,
                kid
            );

            println!("✓ Successfully signed with {} (kid: {})", alg, kid);
        }
    }

    #[test]
    fn test_verify_signed_jwt_with_all_key_types() {
        // Load all private keys
        let keys_dir = "./privatekeys";
        let entries = fs::read_dir(keys_dir).expect("Failed to read privatekeys directory");

        let mut keys = Vec::new();
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                let key_data = fs::read(&path).expect("Failed to read key file");
                let key = Jwk::from_bytes(&key_data).expect("Failed to parse JWK");
                keys.push(key);
            }
        }

        // Test signing and verifying with each key type
        for key in keys.iter() {
            let alg = key.algorithm().unwrap_or("RS256");
            let kid = key.key_id().unwrap_or("unknown");

            // Create test payload
            let mut payload = JwtPayload::new();
            payload.set_issuer("http://localhost:8080");
            payload.set_subject("http://example.com");
            payload.set_issued_at(&SystemTime::now());

            let exp = SystemTime::now() + Duration::from_secs(3600);
            payload.set_expires_at(&exp);
            payload
                .set_claim("test_claim", Some(json!("test_value")))
                .unwrap();

            // Sign the JWT
            let token_str = create_signed_jwt(&payload, &key, None)
                .expect(&format!("Failed to sign with {} (kid: {})", alg, kid));

            // Get public key for verification and set the kid
            let mut public_key_json = key
                .to_public_key()
                .expect(&format!("Failed to get public key for {} ({})", alg, kid));

            // Manually set the kid on the public key since to_public_key doesn't preserve it
            if let Some(kid_value) = key.key_id() {
                let mut pub_key_map = public_key_json.as_ref().clone();
                pub_key_map.insert("kid".to_string(), json!(kid_value));
                public_key_json =
                    Jwk::from_map(pub_key_map).expect("Failed to create public key JWK with kid");
            }

            // Verify the JWT using the existing verify_jwt_with_jwks function
            let mut keymap = Map::new();
            keymap.insert("keys".to_string(), json!([public_key_json.as_ref()]));
            let keyset =
                JwkSet::from_map(keymap).expect("Failed to create JwkSet for verification");

            let result = verify_jwt_with_jwks(&token_str, Some(keyset));
            match &result {
                Ok((verified_payload, _)) => {
                    assert_eq!(verified_payload.issuer().unwrap(), "http://localhost:8080");
                    assert_eq!(verified_payload.subject().unwrap(), "http://example.com");
                    println!(
                        "✓ Successfully verified JWT signed with {} (kid: {})",
                        alg, kid
                    );
                }
                Err(e) => {
                    panic!(
                        "Failed to verify JWT signed with {} (kid: {}): {:?}",
                        alg, kid, e
                    );
                }
            }
        }
    }

    #[test]
    fn test_algorithms_present() {
        // Load all private keys and check we have expected algorithms
        let keys_dir = "./privatekeys";
        let entries = fs::read_dir(keys_dir).expect("Failed to read privatekeys directory");

        let mut algorithms = HashSet::new();
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                let key_data = fs::read(&path).expect("Failed to read key file");
                let key = Jwk::from_bytes(&key_data).expect("Failed to parse JWK");
                if let Some(alg) = key.algorithm() {
                    algorithms.insert(alg.to_string());
                }
            }
        }

        // Check we have at least these algorithms
        let expected_algs = vec![
            "RS256", "PS256", "ES256", "ES384", "ES512", "Ed25519", "Ed448",
        ];

        for alg in expected_algs {
            assert!(
                algorithms.contains(alg),
                "Missing key for algorithm: {}",
                alg
            );
        }

        let mut algs_vec: Vec<_> = algorithms.iter().collect();
        algs_vec.sort();
        println!("✓ All expected algorithms present: {:?}", algs_vec);
    }

    /// Build a minimal valid entity-configuration JWT with inline `jwks` so
    /// `self_verify_jwt` can verify it end-to-end. Used by the iss/sub tests
    /// below.
    fn build_ec_jwt(key: &Jwk, iss: &str, sub: &str) -> String {
        let mut public_key = key.to_public_key().expect("to_public_key");
        if let Some(kid) = key.key_id() {
            let mut pub_map = public_key.as_ref().clone();
            pub_map.insert("kid".to_string(), json!(kid));
            public_key = Jwk::from_map(pub_map).expect("from_map");
        }
        let jwks_value = json!({"keys": [public_key.as_ref()]});

        let mut payload = JwtPayload::new();
        payload.set_issuer(iss);
        payload.set_subject(sub);
        payload.set_issued_at(&SystemTime::now());
        payload.set_expires_at(&(SystemTime::now() + Duration::from_secs(3600)));
        payload
            .set_claim("jwks", Some(jwks_value))
            .expect("set jwks");
        create_signed_jwt(&payload, key, Some("entity-statement+jwt")).expect("sign")
    }

    fn first_private_key() -> Jwk {
        let entries = fs::read_dir("./privatekeys").expect("read privatekeys");
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                let data = fs::read(&path).expect("read key");
                return Jwk::from_bytes(&data).expect("parse JWK");
            }
        }
        panic!("no private keys in ./privatekeys");
    }

    #[test]
    fn test_self_verify_jwt_accepts_matching_iss_sub() {
        let key = first_private_key();
        let token = build_ec_jwt(
            &key,
            "https://entity.example.com",
            "https://entity.example.com",
        );
        let result = self_verify_jwt(&token);
        assert!(
            result.is_ok(),
            "iss==sub entity configuration must verify: {:?}",
            result.err()
        );
        let (payload, _) = result.unwrap();
        assert_eq!(payload.issuer().unwrap(), "https://entity.example.com");
        assert_eq!(payload.subject().unwrap(), "https://entity.example.com");
    }

    #[test]
    fn test_self_verify_jwt_rejects_iss_sub_mismatch() {
        // Spec §3.1: an entity configuration MUST have iss == sub. Without
        // this check, an attacker who controls a signing key could mint a
        // self-signed JWT claiming any other entity as `sub` and have it
        // accepted as that entity's configuration.
        let key = first_private_key();
        let token = build_ec_jwt(
            &key,
            "https://attacker.example.com",
            "https://victim.example.com",
        );
        let result = self_verify_jwt(&token);
        assert!(
            result.is_err(),
            "iss != sub must be rejected by self_verify_jwt"
        );
        let msg = result.err().unwrap().to_string();
        assert!(
            msg.contains("iss") && msg.contains("sub"),
            "error must mention iss/sub mismatch (spec §3.1), got: {msg}"
        );
    }

    /// Build an entity configuration JWT with a caller-supplied `crit` value.
    /// Spec §3.1.1 lets an issuer list critical claim names; the recipient
    /// MUST reject the statement if it doesn't understand any of them.
    fn build_ec_jwt_with_crit(key: &Jwk, iss_sub: &str, crit: Value) -> String {
        let mut public_key = key.to_public_key().expect("to_public_key");
        if let Some(kid) = key.key_id() {
            let mut pub_map = public_key.as_ref().clone();
            pub_map.insert("kid".to_string(), json!(kid));
            public_key = Jwk::from_map(pub_map).expect("from_map");
        }
        let jwks_value = json!({"keys": [public_key.as_ref()]});

        let mut payload = JwtPayload::new();
        payload.set_issuer(iss_sub);
        payload.set_subject(iss_sub);
        payload.set_issued_at(&SystemTime::now());
        payload.set_expires_at(&(SystemTime::now() + Duration::from_secs(3600)));
        payload
            .set_claim("jwks", Some(jwks_value))
            .expect("set jwks");
        payload.set_claim("crit", Some(crit)).expect("set crit");
        create_signed_jwt(&payload, key, Some("entity-statement+jwt")).expect("sign")
    }

    #[test]
    fn test_verify_jwt_rejects_unknown_critical_claim() {
        // Spec §3.1.1: an issuer can use `crit` to require the recipient to
        // understand a listed claim. An unknown name means we cannot safely
        // process the statement.
        let key = first_private_key();
        let token = build_ec_jwt_with_crit(
            &key,
            "https://entity.example.com",
            json!(["totally_unknown"]),
        );
        let result = self_verify_jwt(&token);
        assert!(
            result.is_err(),
            "JWT with unknown critical claim must be rejected"
        );
        let msg = result.err().unwrap().to_string();
        assert!(
            msg.contains("totally_unknown"),
            "error must name the offending claim, got: {msg}"
        );
    }

    #[test]
    fn test_verify_jwt_accepts_known_critical_claim() {
        // `metadata` is a claim this codebase understands, so listing it in
        // `crit` is fine.
        let key = first_private_key();
        let token = build_ec_jwt_with_crit(&key, "https://entity.example.com", json!(["metadata"]));
        let result = self_verify_jwt(&token);
        assert!(
            result.is_ok(),
            "JWT with known critical claim must verify: {:?}",
            result.err()
        );
    }

    #[test]
    fn test_verify_jwt_rejects_non_array_crit() {
        // `crit` must be an array of strings — a scalar value is malformed.
        let key = first_private_key();
        let token = build_ec_jwt_with_crit(&key, "https://entity.example.com", json!("metadata"));
        let result = self_verify_jwt(&token);
        assert!(
            result.is_err(),
            "non-array `crit` claim must be rejected as malformed"
        );
    }

    #[test]
    fn test_is_subordinate_of_exact_match() {
        assert!(is_subordinate_of(
            "https://example.com/fed",
            "https://example.com/fed",
        ));
    }

    #[test]
    fn test_is_subordinate_of_segment_boundary_match() {
        assert!(is_subordinate_of(
            "https://example.com/fed/leaf",
            "https://example.com/fed",
        ));
    }

    #[test]
    fn test_is_subordinate_of_segment_boundary_reject() {
        // `/fed2` is NOT a child of `/fed` even though string-prefix matches.
        assert!(!is_subordinate_of(
            "https://example.com/fed2",
            "https://example.com/fed",
        ));
    }

    #[test]
    fn test_is_subordinate_of_trailing_slash_normalized() {
        assert!(is_subordinate_of(
            "https://example.com/fed/",
            "https://example.com/fed",
        ));
        assert!(is_subordinate_of(
            "https://example.com/fed",
            "https://example.com/fed/",
        ));
    }

    #[test]
    fn test_is_subordinate_of_port_mismatch() {
        assert!(!is_subordinate_of(
            "https://example.com:8443/fed",
            "https://example.com/fed",
        ));
    }

    #[test]
    fn test_is_subordinate_of_scheme_mismatch() {
        assert!(!is_subordinate_of(
            "http://example.com/fed",
            "https://example.com/fed",
        ));
    }

    #[test]
    fn test_is_subordinate_of_host_case_insensitive() {
        assert!(is_subordinate_of(
            "https://EXAMPLE.com/fed",
            "https://example.com/fed",
        ));
    }

    #[test]
    fn test_is_subordinate_of_rejects_subtree_with_query() {
        assert!(!is_subordinate_of(
            "https://example.com/fed",
            "https://example.com/fed?x=1",
        ));
    }

    #[test]
    fn test_is_subordinate_of_entity_query_ignored() {
        assert!(is_subordinate_of(
            "https://example.com/fed/leaf?x=1#frag",
            "https://example.com/fed",
        ));
    }

    #[test]
    fn test_is_subordinate_of_root_subtree() {
        assert!(is_subordinate_of(
            "https://example.com/anything",
            "https://example.com",
        ));
    }

    fn make_payload_with_constraints(c: Value) -> JwtPayload {
        let mut p = JwtPayload::new();
        p.set_claim("constraints", Some(c)).expect("set claim");
        p
    }

    #[test]
    fn test_constraints_from_payload_empty_when_missing() {
        let p = JwtPayload::new();
        let c = Constraints::from_payload(&p).expect("absent constraints is fine");
        assert!(c.max_path_length.is_none());
        assert!(c.permitted_subtrees.is_empty());
        assert!(c.excluded_subtrees.is_empty());
        assert!(c.allowed_entity_types.is_none());
        assert!(c.allowed_leaf_entity_types.is_none());
    }

    #[test]
    fn test_constraints_parsed() {
        let p = make_payload_with_constraints(json!({
            "max_path_length": 2,
            "permitted_subtrees": ["https://a.example/", "https://b.example/"],
            "excluded_subtrees": ["https://bad.example/"],
            "allowed_entity_types": ["openid_provider"],
            "allowed_leaf_entity_types": ["openid_relying_party"],
        }));
        let c = Constraints::from_payload(&p).expect("valid constraints");
        assert_eq!(c.max_path_length, Some(2));
        assert_eq!(c.permitted_subtrees.len(), 2);
        assert_eq!(c.excluded_subtrees, vec!["https://bad.example/"]);
        assert_eq!(
            c.allowed_entity_types.as_deref(),
            Some(["openid_provider".to_string()].as_slice())
        );
        assert_eq!(
            c.allowed_leaf_entity_types.as_deref(),
            Some(["openid_relying_party".to_string()].as_slice())
        );
    }

    #[test]
    fn test_constraints_rejects_non_object() {
        let p = make_payload_with_constraints(json!("oops"));
        assert!(
            Constraints::from_payload(&p).is_err(),
            "non-object constraints must be rejected"
        );
    }

    #[test]
    fn test_constraints_rejects_out_of_range_max_path_length() {
        let p = make_payload_with_constraints(json!({"max_path_length": 9999}));
        let err = Constraints::from_payload(&p).unwrap_err().to_string();
        assert!(err.contains("max_path_length"));
    }

    #[test]
    fn test_constraints_rejects_non_string_subtree() {
        let p = make_payload_with_constraints(json!({"permitted_subtrees": [42]}));
        let err = Constraints::from_payload(&p).unwrap_err().to_string();
        assert!(err.contains("permitted_subtrees"));
    }

    fn empty_types() -> HashSet<String> {
        HashSet::new()
    }

    fn one_type(t: &str) -> HashSet<String> {
        let mut s = HashSet::new();
        s.insert(t.to_string());
        s
    }

    #[test]
    fn test_constraints_max_path_length_pass_and_fail() {
        let c = Constraints {
            max_path_length: Some(2),
            ..Default::default()
        };
        assert!(
            c.check_subject("https://leaf.example", &empty_types(), true, 2)
                .is_ok()
        );
        let err = c
            .check_subject("https://leaf.example", &empty_types(), true, 3)
            .unwrap_err()
            .to_string();
        assert!(err.contains("max_path_length"));
    }

    #[test]
    fn test_constraints_permitted_subtree_required_match() {
        let c = Constraints {
            permitted_subtrees: vec!["https://allowed.example/".into()],
            ..Default::default()
        };
        assert!(
            c.check_subject("https://allowed.example/leaf", &empty_types(), true, 0)
                .is_ok()
        );
        let err = c
            .check_subject("https://other.example/leaf", &empty_types(), true, 0)
            .unwrap_err()
            .to_string();
        assert!(err.contains("permitted_subtree"));
    }

    #[test]
    fn test_constraints_excluded_subtree_rejects() {
        let c = Constraints {
            excluded_subtrees: vec!["https://bad.example/".into()],
            ..Default::default()
        };
        assert!(
            c.check_subject("https://good.example/leaf", &empty_types(), true, 0)
                .is_ok()
        );
        let err = c
            .check_subject("https://bad.example/leaf", &empty_types(), true, 0)
            .unwrap_err()
            .to_string();
        assert!(err.contains("excluded_subtree"));
    }

    #[test]
    fn test_constraints_allowed_entity_types() {
        let c = Constraints {
            allowed_entity_types: Some(vec!["openid_provider".into()]),
            ..Default::default()
        };
        assert!(
            c.check_subject(
                "https://leaf.example",
                &one_type("openid_provider"),
                false,
                1
            )
            .is_ok()
        );
        let err = c
            .check_subject(
                "https://leaf.example",
                &one_type("openid_relying_party"),
                false,
                1,
            )
            .unwrap_err()
            .to_string();
        assert!(err.contains("allowed_entity_types"));
    }

    #[test]
    fn test_constraints_allowed_entity_types_rejects_empty_subject_types() {
        // Fail-closed: a subject with no declared entity types cannot
        // satisfy an allowlist constraint.
        let c = Constraints {
            allowed_entity_types: Some(vec!["openid_provider".into()]),
            ..Default::default()
        };
        let err = c
            .check_subject("https://leaf.example", &empty_types(), false, 1)
            .unwrap_err()
            .to_string();
        assert!(err.contains("allowed_entity_types"));
    }

    #[test]
    fn test_constraints_allowed_leaf_entity_types_rejects_empty_subject_types() {
        let c = Constraints {
            allowed_leaf_entity_types: Some(vec!["openid_provider".into()]),
            ..Default::default()
        };
        let err = c
            .check_subject("https://leaf.example", &empty_types(), true, 0)
            .unwrap_err()
            .to_string();
        assert!(err.contains("allowed_leaf_entity_types"));
    }

    #[test]
    fn test_constraints_allowed_leaf_entity_types_only_at_leaf() {
        let c = Constraints {
            allowed_leaf_entity_types: Some(vec!["openid_provider".into()]),
            ..Default::default()
        };
        // is_leaf=true and type not allowed → reject
        let err = c
            .check_subject(
                "https://leaf.example",
                &one_type("openid_relying_party"),
                true,
                0,
            )
            .unwrap_err()
            .to_string();
        assert!(err.contains("allowed_leaf_entity_types"));
        // is_leaf=false → ignore the leaf constraint
        assert!(
            c.check_subject(
                "https://leaf.example",
                &one_type("openid_relying_party"),
                false,
                1
            )
            .is_ok()
        );
    }

    #[test]
    fn test_walk_context_extracts_entity_types_from_metadata() {
        let mut p = JwtPayload::new();
        p.set_claim(
            "metadata",
            Some(json!({
                "openid_relying_party": {"redirect_uris": []},
                "federation_entity": {}
            })),
        )
        .expect("set metadata");
        let ctx = WalkContext::from_subject_payload("https://leaf.example", &p);
        assert_eq!(ctx.original_subject, "https://leaf.example");
        assert!(
            ctx.original_subject_entity_types
                .contains("openid_relying_party")
        );
        assert!(
            ctx.original_subject_entity_types
                .contains("federation_entity")
        );
    }

    #[test]
    fn test_create_signed_jwt_with_header_sets_trust_chain() {
        // Spec §4.3 — the trust chain may ride along in the JWS header.
        let key = first_private_key();
        let mut payload = JwtPayload::new();
        payload.set_issuer("https://issuer.example");
        payload.set_subject("https://subject.example");
        payload.set_issued_at(&SystemTime::now());
        payload.set_expires_at(&(SystemTime::now() + Duration::from_secs(3600)));
        let chain = vec![
            "jwt-a".to_string(),
            "jwt-b".to_string(),
            "jwt-c".to_string(),
        ];
        let token = create_signed_jwt_with_header(
            &payload,
            &key,
            Some("resolve-response+jwt"),
            Some(&chain),
        )
        .expect("sign");
        // Decode the header without verification to inspect `trust_chain`.
        let parts: Vec<&str> = token.split('.').collect();
        assert_eq!(parts.len(), 3, "JWT should have three segments");
        let header_bytes = base64::engine::general_purpose::URL_SAFE_NO_PAD
            .decode(parts[0])
            .expect("decode header");
        let header_json: Value = serde_json::from_slice(&header_bytes).expect("parse header");
        let header_chain = header_json
            .get("trust_chain")
            .and_then(|v| v.as_array())
            .expect("trust_chain must be an array");
        let recovered: Vec<&str> = header_chain.iter().filter_map(|v| v.as_str()).collect();
        assert_eq!(recovered, vec!["jwt-a", "jwt-b", "jwt-c"]);
    }

    #[test]
    fn test_create_signed_jwt_without_header_omits_trust_chain() {
        // Guardrail: the plain `create_signed_jwt` MUST NOT emit a
        // `trust_chain` header — that header is reserved for explicit
        // produce-on-resolve callers.
        let key = first_private_key();
        let mut payload = JwtPayload::new();
        payload.set_issuer("https://issuer.example");
        payload.set_subject("https://issuer.example");
        payload.set_issued_at(&SystemTime::now());
        payload.set_expires_at(&(SystemTime::now() + Duration::from_secs(3600)));
        let token = create_signed_jwt(&payload, &key, Some("entity-statement+jwt")).expect("sign");
        let parts: Vec<&str> = token.split('.').collect();
        let header_bytes = base64::engine::general_purpose::URL_SAFE_NO_PAD
            .decode(parts[0])
            .expect("decode header");
        let header_json: Value = serde_json::from_slice(&header_bytes).expect("parse header");
        assert!(
            header_json.get("trust_chain").is_none(),
            "default create_signed_jwt must not set trust_chain header"
        );
    }

    /// Build a signed-JWKS JWT whose payload contains the (single-key)
    /// JWKS that signs it — the self-signing pattern §5.2.1 mandates.
    fn build_signed_jwks_body(key: &Jwk) -> String {
        let mut public_key = key.to_public_key().expect("to_public_key");
        if let Some(kid) = key.key_id() {
            let mut pub_map = public_key.as_ref().clone();
            pub_map.insert("kid".to_string(), json!(kid));
            public_key = Jwk::from_map(pub_map).expect("from_map");
        }
        let jwks_value = json!({"keys": [public_key.as_ref()]});
        let mut payload = JwtPayload::new();
        payload.set_issuer("https://entity.example");
        payload.set_subject("https://entity.example");
        payload.set_issued_at(&SystemTime::now());
        payload.set_expires_at(&(SystemTime::now() + Duration::from_secs(3600)));
        payload
            .set_claim("jwks", Some(jwks_value))
            .expect("set jwks");
        create_signed_jwt(&payload, key, Some("jwk-set+jwt")).expect("sign")
    }

    #[test]
    fn test_verify_signed_jwks_body_happy_path() {
        let key = first_private_key();
        let body = build_signed_jwks_body(&key);
        let jwks = verify_signed_jwks_body(&body).expect("verify");
        let expected_kid = key.key_id().expect("kid").to_string();
        assert!(
            !jwks.get(&expected_kid).is_empty(),
            "verified JWKS must contain the signing key (kid={expected_kid})"
        );
    }

    #[test]
    fn test_verify_signed_jwks_body_rejects_tampered_payload() {
        let key = first_private_key();
        let body = build_signed_jwks_body(&key);
        // Flip a byte in the payload segment. The signature will no
        // longer match.
        let parts: Vec<&str> = body.splitn(3, '.').collect();
        let tampered_payload = parts[1]
            .chars()
            .enumerate()
            .map(|(i, c)| if i == 0 && c != 'X' { 'X' } else { c })
            .collect::<String>();
        let tampered = format!("{}.{}.{}", parts[0], tampered_payload, parts[2]);
        assert!(
            verify_signed_jwks_body(&tampered).is_err(),
            "tampered signed JWKS body must be rejected"
        );
    }

    #[test]
    fn test_verify_signed_jwks_body_rejects_missing_inner_jwks() {
        // A JWT whose payload has no inner `jwks` cannot self-verify.
        let key = first_private_key();
        let mut payload = JwtPayload::new();
        payload.set_issuer("https://entity.example");
        payload.set_subject("https://entity.example");
        payload.set_issued_at(&SystemTime::now());
        payload.set_expires_at(&(SystemTime::now() + Duration::from_secs(3600)));
        let body = create_signed_jwt(&payload, &key, Some("jwk-set+jwt")).expect("sign");
        let err = verify_signed_jwks_body(&body).unwrap_err().to_string();
        assert!(
            err.contains("inner `jwks`") || err.contains("No jwks"),
            "error must indicate the missing inner JWKS, got: {err}"
        );
    }

    #[test]
    fn test_verify_signed_jwks_body_rejects_unknown_kid() {
        // A signed-JWKS JWT whose `kid` is not present in the payload's
        // JWKS cannot self-verify — the key resolution step fails.
        let signing_key = first_private_key();
        // Build the body with the real signing key but then mutate the
        // payload's JWKS to a different key. Doing this cleanly requires
        // re-signing with the right key but pointing the kid elsewhere; a
        // simpler proxy is to confirm an inner JWKS that lists a key whose
        // kid doesn't match the JWT header is rejected.
        let mut public_key = signing_key.to_public_key().expect("to_public_key");
        let mut pub_map = public_key.as_ref().clone();
        pub_map.insert("kid".to_string(), json!("different-kid"));
        public_key = Jwk::from_map(pub_map).expect("from_map");
        let jwks_value = json!({"keys": [public_key.as_ref()]});
        let mut payload = JwtPayload::new();
        payload.set_issuer("https://entity.example");
        payload.set_subject("https://entity.example");
        payload.set_issued_at(&SystemTime::now());
        payload.set_expires_at(&(SystemTime::now() + Duration::from_secs(3600)));
        payload
            .set_claim("jwks", Some(jwks_value))
            .expect("set jwks");
        let body = create_signed_jwt(&payload, &signing_key, Some("jwk-set+jwt")).expect("sign");
        assert!(
            verify_signed_jwks_body(&body).is_err(),
            "signed-JWKS body whose header kid is not in the inner JWKS must be rejected"
        );
    }

    #[test]
    fn test_fetch_error_transient_vs_permanent_display() {
        let t = FetchError::transient(Some(5), "5xx from upstream");
        assert!(t.transient);
        assert_eq!(t.retry_after_seconds, Some(5));
        assert!(t.to_string().contains("transient"));
        let p = FetchError::permanent("404 not found");
        assert!(!p.transient);
        assert!(p.retry_after_seconds.is_none());
        assert!(p.to_string().contains("permanent"));
    }

    #[test]
    fn test_fetch_error_downcast_via_anyhow() {
        // Walker / resolve handler distinguish transience via
        // `e.downcast_ref::<FetchError>()`. Confirm round-tripping.
        let wrapped: anyhow::Error = anyhow::Error::new(FetchError::transient(Some(3), "boom"));
        let fe = wrapped.downcast_ref::<FetchError>().expect("downcast");
        assert!(fe.transient);
        assert_eq!(fe.retry_after_seconds, Some(3));
    }

    #[test]
    fn test_compute_retry_sleep_ms_honours_shorter_server_hint() {
        // No upstream hint -> use local backoff verbatim.
        assert_eq!(compute_retry_sleep_ms(500, None), 500);
        // Server says "come back sooner" (300ms) than our backoff (500ms)
        // -> use the shorter server value.
        assert_eq!(compute_retry_sleep_ms(500, Some(0)), 0);
        // Server-supplied value larger than local backoff is *not* honoured;
        // a malicious upstream returning Retry-After: 3600 cannot inflate
        // our wait beyond the next local backoff step.
        assert_eq!(compute_retry_sleep_ms(500, Some(30)), 500);
        // Saturating_mul guard: u64::MAX seconds must not overflow into a
        // shorter sleep.
        assert_eq!(compute_retry_sleep_ms(500, Some(u64::MAX)), 500);
    }

    #[tokio::test]
    async fn test_get_query_classifies_ssrf_as_permanent() {
        // The SSRF gate rejects loopback URLs in production mode; that
        // rejection MUST be classified as permanent so the walker doesn't
        // burn retries and `/resolve` doesn't return 503 for what is
        // really a configuration / policy denial.
        ALLOW_HTTP.store(false, std::sync::atomic::Ordering::Relaxed);
        let err = get_query("http://127.0.0.1/.well-known/openid-federation")
            .await
            .expect_err("loopback URL must be rejected by SSRF gate");
        let fe = err
            .downcast_ref::<FetchError>()
            .expect("error must be a FetchError");
        assert!(!fe.transient, "SSRF rejection must be permanent");
    }

    #[test]
    fn test_known_claims_covers_every_parse_site() {
        // Reflection-style guardrail: every claim name referenced by a
        // `.claim("…")` call in this file must appear in `KNOWN_CLAIMS`. If
        // someone adds a parser for a new claim and forgets to append it
        // here, an issuer that lists the new claim in `crit` would see its
        // (correctly-formed) statement rejected.
        //
        // We grep the file at test time rather than maintaining a separate
        // registry, so the test fails exactly when the source drifts from
        // the constant.
        let src = fs::read_to_string("./src/lib.rs").expect("read lib.rs");
        let mut missing: Vec<String> = Vec::new();
        for line in src.lines() {
            let trimmed = line.trim_start();
            // Skip doc comments and ordinary comments so an example claim
            // name inside documentation doesn't fail the test.
            if trimmed.starts_with("//") {
                continue;
            }
            let mut rest = line;
            while let Some(idx) = rest.find(".claim(\"") {
                let after = &rest[idx + ".claim(\"".len()..];
                if let Some(end) = after.find('"') {
                    let name = &after[..end];
                    if !KNOWN_CLAIMS.contains(&name) && !missing.iter().any(|m| m == name) {
                        missing.push(name.to_string());
                    }
                    rest = &after[end + 1..];
                } else {
                    break;
                }
            }
        }
        assert!(
            missing.is_empty(),
            "every claim name parsed in lib.rs must be in KNOWN_CLAIMS; missing: {missing:?}"
        );
    }
}

#[cfg(test)]
mod ssrf_tests {
    use super::*;

    #[test]
    fn test_is_private_ip_v4() {
        // Loopback
        assert!(is_private_ip(&"127.0.0.1".parse().unwrap()));
        assert!(is_private_ip(&"127.255.255.255".parse().unwrap()));
        // Private ranges
        assert!(is_private_ip(&"10.0.0.1".parse().unwrap()));
        assert!(is_private_ip(&"172.16.0.1".parse().unwrap()));
        assert!(is_private_ip(&"192.168.1.1".parse().unwrap()));
        // Link-local
        assert!(is_private_ip(&"169.254.1.1".parse().unwrap()));
        // Unspecified
        assert!(is_private_ip(&"0.0.0.0".parse().unwrap()));
        // Broadcast
        assert!(is_private_ip(&"255.255.255.255".parse().unwrap()));
        // Public IPs should pass
        assert!(!is_private_ip(&"8.8.8.8".parse().unwrap()));
        assert!(!is_private_ip(&"1.1.1.1".parse().unwrap()));
        assert!(!is_private_ip(&"93.184.216.34".parse().unwrap()));
    }

    #[test]
    fn test_is_private_ip_v6() {
        // Loopback
        assert!(is_private_ip(&"::1".parse().unwrap()));
        // Unspecified
        assert!(is_private_ip(&"::".parse().unwrap()));
        // Unique local (fc00::/7)
        assert!(is_private_ip(&"fc00::1".parse().unwrap()));
        assert!(is_private_ip(&"fd00::1".parse().unwrap()));
        // Link-local (fe80::/10)
        assert!(is_private_ip(&"fe80::1".parse().unwrap()));
        // Public IPv6
        assert!(!is_private_ip(&"2001:db8::1".parse().unwrap()));
        assert!(!is_private_ip(&"2607:f8b0:4004:800::200e".parse().unwrap()));
    }

    #[tokio::test]
    async fn test_validate_rejects_http() {
        let result = validate_federation_url("http://example.com/foo", false).await;
        assert!(result.is_err());
        assert!(
            result
                .unwrap_err()
                .to_string()
                .contains("only HTTPS allowed")
        );
    }

    #[tokio::test]
    async fn test_validate_allows_http_when_configured() {
        // With allow_http=true, HTTP scheme should not be rejected
        let result = validate_federation_url("http://example.com/foo", true).await;
        // Should succeed (allow_http skips all checks after scheme)
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_validate_rejects_non_http_schemes() {
        let result = validate_federation_url("ftp://example.com/foo", false).await;
        assert!(result.is_err());
        assert!(
            result
                .unwrap_err()
                .to_string()
                .contains("only HTTPS allowed")
        );

        let result = validate_federation_url("file:///etc/passwd", false).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_validate_rejects_private_ips() {
        // localhost resolves to 127.0.0.1
        let result = validate_federation_url("https://127.0.0.1/foo", false).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("private/internal"));
    }

    #[tokio::test]
    async fn test_validate_allows_private_ips_in_dev_mode() {
        // With allow_http=true (dev mode), private IPs should be allowed
        let result = validate_federation_url("https://127.0.0.1/foo", true).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_validate_rejects_invalid_url() {
        let result = validate_federation_url("not-a-url", false).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("Invalid URL"));
    }

    #[test]
    fn test_http_client_is_configured() {
        // Verify the shared client was built successfully (lazy_static panics on failure)
        let _ = &*HTTP_CLIENT;
    }

    #[test]
    fn test_validate_redis_key_input_rejects_control_chars() {
        assert_eq!(
            validate_redis_key_input("hello\0world"),
            Err("value contains control characters")
        );
        assert_eq!(
            validate_redis_key_input("hello\nworld"),
            Err("value contains control characters")
        );
        assert_eq!(
            validate_redis_key_input("hello\rworld"),
            Err("value contains control characters")
        );
        assert_eq!(
            validate_redis_key_input("hello\tworld"),
            Err("value contains control characters")
        );
    }

    #[test]
    fn test_validate_redis_key_input_rejects_empty() {
        assert_eq!(validate_redis_key_input(""), Err("empty value"));
    }

    #[test]
    fn test_validate_redis_key_input_rejects_too_long() {
        let long = "a".repeat(2049);
        assert_eq!(validate_redis_key_input(&long), Err("value too long"));
        // Exactly 2048 should be fine
        let exact = "a".repeat(2048);
        assert!(validate_redis_key_input(&exact).is_ok());
    }

    #[test]
    fn test_validate_redis_key_input_accepts_urls() {
        assert!(validate_redis_key_input("https://example.com/trust_mark/foo").is_ok());
        assert!(
            validate_redis_key_input("https://ta.example.org/.well-known/openid-federation")
                .is_ok()
        );
        assert!(validate_redis_key_input("https://entity.example.com:8443/path?q=1").is_ok());
    }

    #[test]
    fn test_validate_entity_type_accepts_known() {
        for etype in KNOWN_ENTITY_TYPES {
            assert!(
                validate_entity_type(etype).is_ok(),
                "should accept {}",
                etype
            );
        }
    }

    #[test]
    fn test_validate_entity_type_rejects_unknown() {
        assert_eq!(
            validate_entity_type("unknown_type"),
            Err("unknown entity type")
        );
        assert_eq!(validate_entity_type(""), Err("unknown entity type"));
        assert_eq!(
            validate_entity_type("openid_provider; DROP TABLE keys"),
            Err("unknown entity type")
        );
    }

    #[test]
    fn test_parse_jwks_json_valid() {
        let json = r#"{"keys":[{"kty":"RSA","n":"test","e":"AQAB","kid":"k1"}]}"#;
        let result = parse_jwks_json(json);
        assert!(result.is_ok());
        let keyset = result.unwrap();
        assert!(!keyset.get("k1").is_empty());
    }

    #[test]
    fn test_parse_jwks_json_no_keys_field() {
        let json = r#"{"not_keys":[]}"#;
        let result = parse_jwks_json(json);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("No 'keys' field"));
    }

    #[test]
    fn test_parse_jwks_json_invalid_json() {
        let result = parse_jwks_json("not json");
        assert!(result.is_err());
    }

    #[test]
    fn test_get_jwks_from_payload_missing_jwks() {
        let payload = JwtPayload::new();
        let result = get_jwks_from_payload(&payload);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("No jwks"));
    }

    #[test]
    fn test_get_jwks_from_payload_with_jwks() {
        let mut payload = JwtPayload::new();
        payload
            .set_claim(
                "jwks",
                Some(json!({"keys":[{"kty":"RSA","n":"test","e":"AQAB","kid":"k1"}]})),
            )
            .unwrap();
        let result = get_jwks_from_payload(&payload);
        assert!(result.is_ok());
    }
}
