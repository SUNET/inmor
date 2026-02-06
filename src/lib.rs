#![allow(unused)]
use anyhow::{Result, anyhow, bail};

use lazy_static::lazy_static;
use log::{debug, info};
use redis::AsyncCommands;
use redis::Client;
use reqwest::blocking;
use sha2::{Digest, Sha256};
use std::fmt::{Display, format};

use actix_web::{
    App, HttpRequest, HttpResponse, HttpServer, Responder, error, get, middleware, post, web,
};
use actix_web_lab::extract::Query;

use actix_web::http::uri::Parts;
use base64::Engine;
use josekit::{
    JoseError,
    jwk::{Jwk, JwkSet},
    jws::alg::rsassa::RsassaJwsAlgorithm,
    jws::{
        ES256, ES384, ES512, EdDSA, JwsAlgorithm, JwsHeader, JwsSigner, JwsVerifier, PS256, RS256,
    },
    jwt::{self, JwtPayload, JwtPayloadValidator},
    util,
};
use oidfed_metadata_policy::*;
use serde::Serialize;
use serde::{Deserialize, de::Error};
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
    static ref PRIVATE_KEY: Vec<u8> = std::fs::read("./private.json").unwrap();
}
pub const WELL_KNOWN: &str = ".well-known/openid-federation";

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
    pub entity_type: String,
    pub has_trustmark: bool,
    pub trustmarks: HashSet<String>,
}

impl EntityDetails {
    pub fn new(entity_id: &str, entity_type: &str, trustmarks: Option<&Value>) -> Self {
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
            entity_type: entity_type.to_string(),
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
    display_name: Option<String>,
    description: Option<String>,
    logo_uri: Option<String>,
    policy_uri: Option<String>,
    information_uri: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct EntityCollectionResponse {
    pub entity_id: String,
    pub entity_types: Vec<String>,
    pub ui_infos: Option<HashMap<String, UiInfo>>,
}

impl EntityCollectionResponse {
    pub fn new(entity_id: String, entity_types: Vec<String>) -> Self {
        EntityCollectionResponse {
            entity_id,
            entity_types,
            ui_infos: None,
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
}

impl ServerConfiguration {
    pub fn new(
        domain: String,
        redis_uri: String,
        tls_cert: Option<String>,
        tls_key: Option<String>,
    ) -> ServerConfiguration {
        ServerConfiguration {
            domain: URL(domain),
            redis_uri,
            tls_cert,
            tls_key,
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
        ServerConfiguration::new(domain, redis, tls_cert, tls_key)
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
    let mut header = JwsHeader::new();
    header.set_token_type("JWT");

    // Set custom token type if provided
    if let Some(typ) = token_type {
        header.set_claim("typ", Some(json!(typ)))?;
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

    // Set kid from the key
    if let Some(kid) = key.key_id() {
        header.set_key_id(kid);
    }

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

/// This method returns the corresponding entitys based on given
/// entity type. Used in fetch_collection endpoint.
pub async fn get_entitycollectionresponse(
    entity_type: &str,
    redis: web::Data<redis::Client>,
) -> Result<Vec<EntityCollectionResponse>> {
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(|e| anyhow::Error::msg(format!("Failed to get Redis connection: {}", e)))?;
    let mut result: Vec<EntityCollectionResponse> = Vec::new();
    match entity_type {
        "openid_provider" => {
            let mut res = (redis::Cmd::smembers("inmor:op")
                .query_async::<Vec<String>>(&mut conn)
                .await)
                .unwrap_or_default();
            // Now loop over
            for entry in res {
                let entry_struct = EntityCollectionResponse::new(
                    entry,
                    vec![
                        "federation_entity".to_string(),
                        "openid_provider".to_string(),
                    ],
                );
                result.push(entry_struct);
            }
        }
        "openid_relying_party" => {
            let mut res = (redis::Cmd::smembers("inmor:rp")
                .query_async::<Vec<String>>(&mut conn)
                .await)
                .unwrap_or_default();
            // Now loop over
            for entry in res {
                let entry_struct = EntityCollectionResponse::new(
                    entry,
                    vec![
                        "federation_entity".to_string(),
                        "openid_relying_party".to_string(),
                    ],
                );
                result.push(entry_struct);
            }
        }
        "taia" => {
            let mut res = (redis::Cmd::smembers("inmor:taia")
                .query_async::<Vec<String>>(&mut conn)
                .await)
                .unwrap_or_default();
            // Now loop over
            for entry in res {
                let entry_struct =
                    EntityCollectionResponse::new(entry, vec!["federation_entity".to_string()]);
                result.push(entry_struct);
            }
        }
        _ => (),
    }
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
                    eprintln!("Failed to parse JWT for entity {}: {}", key, e);
                    continue; // Skip invalid JWTs instead of panicking
                }
            };
            let Some(metadata) = payload.claim("metadata") else {
                eprintln!("Missing metadata claim for entity: {}", key);
                continue; // Skip if no metadata
            };
            let trustmarks = payload.claim("trust_marks");
            let Some(x) = metadata.as_object() else {
                eprintln!("Metadata is not an object for entity: {}", key);
                continue; // Skip if metadata is not an object
            };
            if x.contains_key("openid_provider") {
                // Means OP
                let entity = EntityDetails::new(key, "openid_provider", trustmarks);
                results.push(entity);
            } else if x.contains_key("openid_relying_party") {
                // Means RP
                let entity = EntityDetails::new(key, "openid_relying_party", trustmarks);

                results.push(entity);
            } else {
                // Means TA/IA
                let entity = EntityDetails::new(key, "taia", trustmarks);
                results.push(entity);
            }
        }
    }
    // Now let us go through the list if we need to filter based on the query parameter.
    if let Some(etype) = entity_type {
        // Means an entity_type was passed.
        results.retain(|x| etype.contains(&x.entity_type));
    }

    if let Some(inter) = intermediate {
        // Means we should only provide any intermediate subordinate
        results.retain(|x| match x.entity_type.as_str() {
            "taia" => inter, // When we asked for intermediate
            _ => !inter,     // When we want to the rest
        });
    }

    if let Some(true) = trust_marked {
        // Means check if at least one trustmark exists
        results.retain(|x| x.has_trustmark);
    }
    if let Some(trust_mark_type) = trust_mark_type {
        // Means filter based on trustmark type

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

///https://zachmann.github.io/openid-federation-entity-collection/main.html
/// Entity collection endpoint, from Zachmann's draft.
#[get("/collection")]
pub async fn fetch_collections(
    req: HttpRequest,
    redis: web::Data<redis::Client>,
) -> actix_web::Result<impl Responder> {
    let params: Vec<(String, String)> =
        match web::Query::<Vec<(String, String)>>::from_query(req.query_string()) {
            Ok(data) => data.to_vec(),
            Err(_) => return Err(error::ErrorBadRequest("Missing params")),
        };

    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let mut entity_type_asked = false;

    let mut result: Vec<EntityCollectionResponse> = Vec::new();
    for (q, p) in params.iter() {
        if (q == "entity_type") {
            // Means we were asked an entity type
            entity_type_asked = true;
            match p.as_str() {
                "openid_provider" => {
                    let internal = get_entitycollectionresponse("openid_provider", redis.clone())
                        .await
                        .map_err(error::ErrorInternalServerError)?;
                    result.extend(internal);
                }
                "openid_relying_party" => {
                    let internal =
                        get_entitycollectionresponse("openid_relying_party", redis.clone())
                            .await
                            .map_err(error::ErrorInternalServerError)?;
                    result.extend(internal);
                }

                _ => (),
            }
        } else {
            // We don't support the other query parameters yet.
            // https://zachmann.github.io/openid-federation-entity-collection/main.html#section-2.2.1 has all
            // the details.
            eprintln!("Unsupported query parameter in /collection: {}", q);
            return error_response_400("unsupported_parameter", "{q}");
        }
    }

    // If no entity type was asked, we should return all types.
    if !entity_type_asked {
        let internal = get_entitycollectionresponse("openid_provider", redis.clone())
            .await
            .map_err(error::ErrorInternalServerError)?;
        result.extend(internal);
        let internal = get_entitycollectionresponse("openid_relying_party", redis.clone())
            .await
            .map_err(error::ErrorInternalServerError)?;
        result.extend(internal);

        let internal = get_entitycollectionresponse("taia", redis)
            .await
            .map_err(error::ErrorInternalServerError)?;
        result.extend(internal);
    }

    Ok(HttpResponse::Ok()
        .content_type("application/json")
        .body(json!(result).to_string()))
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
        None => return Err(error::ErrorInternalServerError("Missing sub parameter")),
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
            eprintln!("Subordinate not found in Redis for sub={}: {}", sub, e);
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
            eprintln!("No jwks claim found in payload");
            return Err(anyhow::Error::msg("No jwks was found in the payload"));
        }
    };
    let keys = match jwks_data.get("keys") {
        Some(data) => data,
        None => {
            eprintln!("No keys field found in jwks claim");
            return Err(anyhow::Error::msg(
                "No keys was found in jwks in the payload",
            ));
        }
    };
    let mut internal_map: Map<String, Value> = Map::new();
    internal_map.insert("keys".to_string(), keys.clone());

    Ok(JwkSet::from_map(internal_map)?)
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

/// Verify JWT against given JWKS
pub fn verify_jwt_with_jwks(data: &str, keys: Option<JwkSet>) -> Result<(JwtPayload, JwsHeader)> {
    // Code to find the header & payload without any verification
    let (payload, header) = get_unverified_payload_header(data)?; // Now either use the passed one or use self keys
    let jwks = match keys {
        Some(d) => d,
        None => get_jwks_from_payload(&payload)?,
    };
    let kid = header
        .key_id()
        .ok_or_else(|| anyhow::Error::msg("Missing key ID in JWT header"))?;
    // Let us find the key used to sign the JWT
    let keys = jwks.get(kid);
    if keys.is_empty() {
        // means we can not find the key used to sign this.
        return Err(anyhow::Error::msg("Can not find kid used to sign."));
    }
    let key = keys[0];
    // Create the appropriate verifier based on the algorithm
    let algorithm = header
        .algorithm()
        .ok_or_else(|| anyhow::Error::msg("Missing algorithm in JWT header"))?;
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
    // Now we should also validate the JWT
    // See more https://github.com/SUNET/inmor/issues/79
    let mut validator = JwtPayloadValidator::new();
    validator.set_base_time(SystemTime::now());
    validator.validate(&payload)?;
    Ok((payload, header))
}

/// This function will self veify the JWT and returns
/// the payload and header after verification.
pub fn self_verify_jwt(data: &str) -> Result<(JwtPayload, JwsHeader)> {
    let (payload, header) = get_unverified_payload_header(data)?;
    let jwks = get_jwks_from_payload(&payload)?;
    let (payload, header) = verify_jwt_with_jwks(data, Some(jwks))?;
    Ok((payload, header))
}

/// This function will walk through a subordinate's tree of entities.
/// Means you point it to a TA/IA and it will traverse the whole tree.
pub fn tree_walking(entity_id: &str, conn: &mut redis::Connection) {
    // First let us get the entity configuration
    let jwt_net = match get_jwt_sync(entity_id) {
        Ok(res) => res,
        Err(e) => {
            eprintln!(
                "Failed to fetch entity configuration for {}: {}",
                entity_id, e
            );
            return;
        }
    };

    // Verify and get the payload
    let (entity_payload, _) = match self_verify_jwt(&jwt_net) {
        Ok(data) => data,
        Err(e) => {
            eprintln!(
                "Failed to verify entity configuration for {}: {}",
                entity_id, e
            );
            return;
        }
    };

    // Add to the visisted list
    match redis::Cmd::sadd("inmor:current_visited", entity_id).query::<String>(conn) {
        Ok(_) => (),
        Err(e) => return,
    }
    // Add to the entity hash in redis
    match redis::Cmd::hset("inmor:entities", entity_id, jwt_net.as_bytes()).query::<String>(conn) {
        Ok(_) => (),
        Err(e) => return,
    }

    // Visit authorities for authority statements
    if let Some(value) = entity_payload.claim("authority_hints") {
        // We need to traverse the authorities
        fetch_all_subordinate_statements(value, entity_id, conn);
    }

    // Now the actual discovery
    let metadata = match entity_payload.claim("metadata") {
        Some(value) => match value.as_object() {
            Some(obj) => obj,
            None => return,
        },
        None => return,
    };

    if metadata.get("openid_relying_party").is_some() {
        // Means RP
        let _ = redis::Cmd::sadd("inmor:rp", entity_id).query::<String>(conn);
    } else if metadata.get("openid_provider").is_some() {
        // Means OP

        let _ = redis::Cmd::sadd("inmor:op", entity_id).query::<String>(conn);
    } else {
        // Means a TA/IA.
        match redis::Cmd::sadd("inmor:taia", entity_id).query::<String>(conn) {
            Ok(_) => (),
            Err(_) => return,
        }
        // Getting the list endpoint if any
        let list_endpoint = match metadata.get("federation_entity") {
            Some(f_entity) => f_entity.get("federation_list_endpoint"),
            None => None,
        };

        if list_endpoint.is_none() {
            // Means no list endpoint avaiable
            // TODO: add debug point here
            return;
        }
        if let Some(endpoint) = list_endpoint.and_then(|e| e.as_str())
            && let Ok(resp) = get_query_sync(endpoint)
        {
            // Here we will loop through the subordinates
            if let Ok(subs) = serde_json::from_str::<Value>(&resp)
                && let Some(sub_array) = subs.as_array()
            {
                for sub in sub_array {
                    if let Some(sub_str) = sub.as_str() {
                        let ismember = redis::Cmd::sismember("inmor:current_visited", sub_str)
                            .query::<bool>(conn)
                            .unwrap_or_default();
                        if ismember {
                            // Means we already visited it, it is a loop
                            // We should skip it.
                            info!("We have a loop: {sub_str}");
                            continue;
                        }
                        // Means we have a new subordinate
                        info!("Found new subordinate: {sub_str}");
                        queue_lpush(sub_str, conn);
                    }
                }
            }
        }
    }
}

// To push to the queue for the next set of visists
pub fn queue_lpush(entity_id: &str, conn: &mut redis::Connection) {
    redis::Cmd::lpush("inmor:visit_subordinate", entity_id)
        .query::<bool>(conn)
        .unwrap_or_default();
}

// To blocked wait on the queue
pub fn queue_wait(conn: &mut redis::Connection) -> String {
    match redis::Cmd::brpop("inmor:visit_subordinate", 0.0).query::<(String, String)>(conn) {
        Ok(val) => {
            println!("Received {val:?} inside.");
            val.1
        }
        Err(e) => {
            println!("{e:?}");
            "".to_string()
        }
    }
}

/// Fetches the subordinate statements and stores on memory as required.
pub fn fetch_all_subordinate_statements(
    authority_hints: &Value,
    entity_id: &str,
    conn: &mut redis::Connection,
) {
    let Some(ahints) = authority_hints.as_array() else {
        return; // Skip if not an array
    };
    for ahint in ahints.iter() {
        let Some(ahint_str) = ahint.as_str() else {
            continue; // Skip if not a string
        };
        // HACK: Enable TA hack here
        // TODO: ^^
        println!("Fetching {ahint_str:?}");
        let jwt_net = match get_jwt_sync(ahint_str) {
            Ok(res) => res,
            Err(e) => {
                eprintln!("Failed to fetch authority hint {}: {}", ahint_str, e);
                return;
            }
        };

        // Verify and get the payload
        let (entity_payload, _) = match self_verify_jwt(&jwt_net) {
            Ok(data) => data,
            Err(e) => {
                eprintln!(
                    "Failed to verify authority hint JWT for {}: {}",
                    ahint_str, e
                );
                return;
            }
        };

        let metadata = match entity_payload.claim("metadata") {
            Some(value) => match value.as_object() {
                Some(obj) => obj,
                None => {
                    eprintln!("Metadata is not an object for authority: {}", ahint_str);
                    continue;
                }
            },
            None => {
                eprintln!("Missing metadata claim for authority: {}", ahint_str);
                continue;
            }
        };

        // First get the federation_entity map inside of the JSOn
        let fed_entity = match metadata.get("federation_entity") {
            Some(value) => match value.as_object() {
                Some(obj) => obj,
                None => {
                    eprintln!("federation_entity is not an object for: {}", ahint_str);
                    continue;
                }
            },
            None => {
                eprintln!("Missing federation_entity in metadata for: {}", ahint_str);
                continue;
            }
        };
        // Then the fetch_end_point
        let fetch_endpoint = fed_entity.get("federation_fetch_endpoint");

        println!("SEE {fetch_endpoint:?}");
        if let Some(fetch_endpoint) = fetch_endpoint {
            // HACK: Enable TA hack here
            // TODO: ^^
            //let fetch_endpoint = fetch_endpoint.unwrap();
            let sub_statement =
                fetch_sub_statement_sync(fetch_endpoint.as_str().unwrap(), entity_id);
            if let Ok((jwt_str, url)) = sub_statement {
                // Store it on memeory
                match redis::Cmd::hset("inmor:subordinate_query", url, jwt_str.as_bytes())
                    .query::<String>(conn)
                {
                    Ok(_) => (),
                    Err(e) => return,
                }
            }
        }
    }
}

pub async fn resolve_entity_to_trustanchor(
    sub: &str,
    trust_anchors: Vec<&str>,
    start: bool,
    visited: &mut HashSet<String>,
) -> Result<Vec<VerifiedJWT>> {
    eprintln!("\nReceived {sub} with trust anchors {trust_anchors:?}");

    let empty_authority: Vec<String> = Vec::new();
    let eal = json!(empty_authority);

    // This will hold the list of trust chain
    let mut result = Vec::new();

    // to stop infinite loop
    // First get the entity configuration and self verify
    let original_ec = match get_entity_configruation_as_jwt(sub).await {
        Ok(res) => res,
        Err(e) => {
            eprintln!("Failed to fetch entity configuration for {}: {}", sub, e);
            return Ok(result); // Read FOUND_TA section in code to find why it is okay to
            // result a half done list back.
        }
    };
    // Add it already visited
    visited.insert(sub.to_string());

    let (opayload, oheader) = self_verify_jwt(&original_ec)?;

    if start {
        let vjwt = VerifiedJWT::new(original_ec, &opayload, false, false);
        result.push(vjwt);
    }
    // FIXME: Store the singing KID from the header so that we can verify it below.

    // Now find the authority_hints
    let authority_hints = match opayload.claim("authority_hints") {
        Some(v) => v,
        // Means we are at one Trust anchor (most probably)
        None => &eal,
    };
    println!("\nAuthority hints: {authority_hints:?}\n");
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
        // Fetch the authority's entity configuration
        let ah_jwt = match get_entity_configruation_as_jwt(ah_entity).await {
            Ok(res) => res,
            Err(e) => {
                eprintln!(
                    "Failed to fetch authority entity configuration for {}: {}",
                    ah_entity, e
                );
                return Ok(result); // Read FOUND_TA section in code to find why it is okay to
                // result a half done list back.
            }
        };

        // Verify and get the payload
        let jwt_result = self_verify_jwt(&ah_jwt);
        if jwt_result.is_err() {
            eprintln!(
                "Failed to verify authority JWT for {}: {:?}",
                ah_entity,
                jwt_result.err()
            );
            continue;
        }

        let (ah_payload, _) = jwt_result.expect("This can not be error here.");
        let Some(ah_metadata) = ah_payload.claim("metadata") else {
            eprintln!("Missing metadata in authority payload for: {}", ah_entity);
            continue;
        };
        let Some(federation_entity) = ah_metadata.get("federation_entity") else {
            eprintln!("Missing federation_entity in metadata for: {}", ah_entity);
            continue;
        };
        let Some(fetch_endpoint) = federation_entity.get("federation_fetch_endpoint") else {
            eprintln!("Missing federation_fetch_endpoint for: {}", ah_entity);
            continue;
        };
        let Some(fetch_endpoint_str) = fetch_endpoint.as_str() else {
            eprintln!(
                "federation_fetch_endpoint is not a string for: {}",
                ah_entity
            );
            continue;
        };
        // Fetch the entity statement/ subordinate statement
        let sub_statement = match fetch_subordinate_statement(fetch_endpoint_str, sub).await {
            Ok(res) => res,
            Err(e) => {
                eprintln!(
                    "Failed to fetch subordinate statement for {} from {}: {}",
                    sub, ah_entity, e
                );
                return Ok(result); // Read FOUND_TA section in code to find why it is okay to
                // result a half done list back.
            }
        };
        // Get the authority's JWKS and then verify the subordinate statement against them.
        let ah_jwks = match get_jwks_from_payload(&ah_payload) {
            Ok(result) => result,
            Err(e) => {
                eprintln!(
                    "Failed to get JWKS from authority payload for {}: {}",
                    ah_entity, e
                );
                continue;
            }
        };
        let (subs_payload, _) = match verify_jwt_with_jwks(&sub_statement, Some(ah_jwks)) {
            Ok(value) => value,
            Err(e) => {
                eprintln!(
                    "Failed to verify subordinate statement for {} from {}: {}",
                    sub, ah_entity, e
                );
                continue;
            }
        };
        // FIXME: An Entity Statement is signed using a key from the jwks claim in the next.
        // Restating this symbolically, for each j = 0,...,i-1, ES[j] is signed by
        // a key in ES[j+1]["jwks"].
        // Means now we should verify that the subject's signing key is one of the key in the JWKS
        // of the subordinate statment.
        if ta_flag {
            // Means this is the end of resolving
            let vjwt = VerifiedJWT::new(sub_statement, &subs_payload, true, false);
            result.push(vjwt);
            let ajwt = VerifiedJWT::new(ah_jwt.clone(), &ah_payload, false, true);
            result.push(ajwt);
            return Ok(result);
        } else {
            // Now do a recursive query
            let r_result = Box::pin(resolve_entity_to_trustanchor(
                ah_entity,
                trust_anchors.clone(),
                false,
                visited,
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
    let min_exp = result
        .iter()
        .filter_map(|v| v.payload.expires_at())
        .min()
        .unwrap_or(fallback_exp);
    payload.set_expires_at(&min_exp);

    if let Some(metadata_val) = metadata {
        payload.set_claim("metadata", Some(json!(metadata_val)));
    }
    let trust_chain: Vec<String> = result.iter().map(|x| x.jwt.clone()).collect();
    let _ = payload.set_claim("trust_chain", Some(json!(trust_chain)));

    // Signing JWT
    let keydata = &*PRIVATE_KEY.clone();
    let key = Jwk::from_bytes(keydata)?;

    create_signed_jwt(&payload, &key, Some("resolve-response+jwt"))
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
    // Now loop over the trust_anchors
    let result = match resolve_entity_to_trustanchor(&sub, tas, true, &mut visisted).await {
        Ok(res) => res,
        Err(e) => {
            eprintln!("Error resolving entity {} to trust anchors: {}", sub, e);
            return error_response_400("invalid_trust_chain", "Failed to find trust chain");
        }
    };

    // Verify that the result is not empty and we actually found a TA
    if result.is_empty() {
        eprintln!("Empty trust chain result for entity: {}", sub);
        return error_response_400("invalid_trust_chain", "Failed to find trust chain");
    }
    if result.iter().any(|i| i.taresult) {
        // Means we found our trust anchor
        // FOUND_TA: Here if verify if we actually found any of the TA we wanted.
        found_ta = true;
    }
    if !found_ta {
        eprintln!("No trust anchor found in chain for entity: {}", sub);
        return error_response_400("invalid_trust_chain", "Failed to find trust chain");
    }

    let mut mpolicy: Option<Map<String, Value>> = None;
    let reversed: Vec<&VerifiedJWT> = result.iter().rev().collect();

    // We need to skip the top one (the trust anchor's entity configuration)
    for (i, res) in reversed.iter().enumerate().skip(1) {
        println!("\n{:?}\n", res.payload);
        mpolicy = match mpolicy {
            // This is when we have some policy the higher subordinate statement
            Some(mut val) => {
                // But we should only apply claim from subordinate statements
                if res.substatement {
                    let new_policy = res.payload.claim("metadata_policy");
                    match new_policy {
                        Some(p) => {
                            let temp_val = json!(val);
                            // Uncomment these to learn about metadata policy merging
                            //println!("\n Calling with {:?}\n\n{:?}\n\n\n", &temp_val, p);
                            let merged = merge_policies(&temp_val, p);
                            match merged {
                                Ok(policy) => Some(policy),
                                Err(_) => {
                                    return error_response_400(
                                        "invalid_trust_chain",
                                        "Failed in merging metadata policy",
                                    );
                                }
                            }
                        }
                        None => Some(val),
                    }
                } else {
                    // Means the final entity statement
                    // We should now apply the merged policy at val to the metadata claim
                    let Some(mut metadata) = res.payload.claim("metadata").cloned() else {
                        return error_response_400(
                            "invalid_trust_chain",
                            "missing metadata in entity statement",
                        );
                    };
                    eprintln!(
                        "\nFinal policy checking: val= {:?}\n\n metadata= {:?}\n\n",
                        &val, metadata
                    );
                    let mut forced_metadata: Option<&Value> = None;
                    // Let us see if we have any subordinate statement's metadata to apply first
                    if (i > 0) {
                        let last_sub_statement = reversed[i - 1];
                        forced_metadata = last_sub_statement.payload.claim("metadata");
                    }
                    let Some(metadata_obj) = metadata.as_object() else {
                        return error_response_400(
                            "invalid_trust_chain",
                            "metadata is not an object",
                        );
                    };
                    let full_policy = json!({"metadata_policy": val.clone(), "metadata": forced_metadata.clone()});
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
                            eprintln!(
                                "\nApplied final metadata after applying policy: {:?}\n\n",
                                &applied
                            );
                            Some(applied)
                        }
                        Err(_) => {
                            eprintln!("Failed in applying metadata policy on metadata");
                            return error_response_400(
                                "invalid_trust_chain",
                                "received error in applying metadata policy on metadata",
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
    eprintln!("After the whole call: {mpolicy:?}\n");
    // The mpolicy now contains the final metadata after applying policies.

    // Apply entity_type filtering if provided
    // Per OpenID Federation spec, entity_type filters which metadata keys are returned.
    // If entity_type is provided but none of the types match, return all metadata.
    let filtered_metadata = filter_metadata_by_entity_types(mpolicy, entity_type.as_ref());

    // If we reach here means we have a list of JWTs and also verified metadata.
    let resp = create_resolve_response_jwt(&state, &sub, &result, filtered_metadata)
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

/// Internal function to apply forced metadata from subordinate statement on top of
/// the metadata of the final entity statement.
fn merge_objects(v1: &mut Value, v2: &Value) {
    if let (Some(obj1), Some(obj2)) = (v1.as_object_mut(), v2.as_object()) {
        for (key, value) in obj2 {
            obj1.insert(key.clone(), value.clone());
        }
    }
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
        eprintln!("Trust mark not found in Redis: hash={}", trust_mark_hash);
        return error_response_404("not_found", "Trust mark not found.");
    }

    let mut invalid = false;
    let mut expired = false;

    let jwks = state.public_keyset.clone();
    let (payload, _) = match verify_jwt_with_jwks(&trust_mark, Some(jwks)) {
        Ok((payload, header)) => (payload, header),
        Err(err) => {
            if err
                .to_string()
                .contains("Invalid claim: The token has expired")
            {
                expired = true;
            } else {
                invalid = true;
            }
            (JwtPayload::new(), JwsHeader::new())
        }
    };
    let mut status = "";
    if invalid {
        status = "invalid";
    } else if expired {
        status = "expired";
    } else {
        let v = json!("");
        let hkey = "inmor:tm:".to_string() + payload.subject().unwrap_or("");
        let claims = payload.claims_set();
        let trustmarktype = claims
            .get("trust_mark_type")
            .unwrap_or(&v)
            .as_str()
            .unwrap_or("");

        let mark = redis::Cmd::hget(hkey, trustmarktype)
            .query_async::<String>(&mut conn)
            .await
            .map_err(error::ErrorInternalServerError)?;

        if mark != "revoked" {
            status = "active";
        } else {
            status = "revoked";
        }
    }

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
    state: web::Data<AppState>,
) -> actix_web::Result<HttpResponse> {
    let TrustMarkListParams {
        trust_mark_type,
        sub,
    } = info.into_inner();

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
            //let mut result = res.unwrap();
            if let Some(sub_entity) = sub {
                // Means we have a sub value to check
                //let sub_entity = sub.unwrap();
                if result.contains(&sub_entity) {
                    result = vec![sub_entity];
                } else {
                    // Means so such sub for the trust_mark_type in redis
                    return Ok(HttpResponse::NotFound().body(""));
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
        Err(_) => Ok(HttpResponse::NotFound().body("")),
    }
}

///
/// https://openid.net/specs/openid-federation-1_0.html#section-8.6.1
#[get("/trust_mark")]
pub async fn trust_mark_query(
    info: Query<TrustMarkParams>,
    redis: web::Data<redis::Client>,
    state: web::Data<AppState>,
) -> actix_web::Result<HttpResponse> {
    let TrustMarkParams {
        trust_mark_type,
        sub,
    } = info.into_inner();

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
            eprintln!(
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

/// Gets subordinate statement in sync
pub fn fetch_sub_statement_sync(fetch_url: &str, entity_id: &str) -> Result<(String, String)> {
    let url = format!("{fetch_url}?sub={entity_id}");
    debug!("FETCH {url}");
    match get_query_sync(&url) {
        Ok(res) => Ok((res, url)),
        Err(e) => Err(e),
    }
}

/// Gets the enitity configuration of a given entity_id for sync code.
pub fn get_jwt_sync(entity_id: &str) -> Result<String> {
    let url = format!("{entity_id}/{WELL_KNOWN}");
    get_query_sync(&url)
}

/// GET call for sync code
pub fn get_query_sync(url: &str) -> Result<String> {
    let resp = match ureq::get(url).call() {
        Ok(mut body) => body.body_mut().read_to_string()?,
        Err(e) => return Err(anyhow::Error::new(e)),
    };
    Ok(resp)
}

/// To do a GET query
pub async fn get_query(url: &str) -> Result<String> {
    Ok(reqwest::get(url).await?.text().await?)
}

/// FIXME: as an example.
/// This function will add a new sub-ordinate entity to
/// a Trust Anchor or intermediate.
pub async fn add_subordinate(entity_id: &str) -> Result<String> {
    let data = get_entity_configruation_as_jwt(entity_id).await?;

    self_verify_jwt(&data);
    Ok("all good".to_string())
}

pub fn error_response_404(edetails: &str, message: &str) -> actix_web::Result<HttpResponse> {
    Ok(HttpResponse::NotFound()
        .content_type("application/json")
        .body(format!(
            "{{\"error\":\"{edetails}\",\"error_description\": \"{message}\"}}"
        )))
}

pub fn error_response_400(edetails: &str, message: &str) -> actix_web::Result<HttpResponse> {
    Ok(HttpResponse::BadRequest()
        .content_type("application/json")
        .body(format!(
            "{{\"error\":\"{edetails}\",\"error_description\": \"{message}\"}}"
        )))
}

#[cfg(test)]
mod tests {
    use super::*;
    use josekit::jwt;
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
}
