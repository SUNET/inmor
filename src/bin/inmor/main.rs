#![allow(unused)]

use actix_web::{
    App, HttpRequest, HttpResponse, HttpServer, Responder, error, get, middleware, web,
};
use lazy_static::lazy_static;
use redis::Client;
use redis::Commands;
use serde::Deserialize;
use serde::Serialize;
use std::fmt::format;
use std::fs;
use std::ops::Deref;
use std::sync::Mutex;
use std::{env, io};

use clap::Parser;
use inmor::*;
use josekit::{
    JoseError,
    jwk::{Jwk, JwkSet},
    jws::{JwsHeader, RS256},
    jwt::{self, JwtPayload},
};
use rustls::ServerConfig;
use rustls_pemfile::{certs, pkcs8_private_keys};
use serde_json::{Map, Value, json};
use std::collections::HashMap;
use std::time::{Duration, SystemTime};

lazy_static! {
    static ref TERA: tera::Tera = {
        let mut tera = tera::Tera::new("templates/**/*").expect("Failed to load templates");
        tera.autoescape_on(vec![".html"]);
        tera
    };
}

async fn get_from_cache(redis: web::Data<redis::Client>) -> actix_web::Result<impl Responder> {
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let res = redis::Cmd::get("name")
        .query_async::<String>(&mut conn)
        .await
        .map_err(error::ErrorInternalServerError)?;

    Ok(HttpResponse::Ok().body(res))
}

#[derive(Serialize, Deserialize)]
pub struct MyParams {
    name: String,
}

#[get("/")]
async fn index(
    redis: web::Data<redis::Client>,
    app_state: web::Data<AppState>,
) -> actix_web::Result<impl Responder> {
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    // Fetch entity configuration JWT
    let entity_jwt: Option<String> = redis::Cmd::get("inmor:entity_id")
        .query_async(&mut conn)
        .await
        .ok();

    // Decode entity config for display
    let mut ta_name = String::new();
    let mut endpoints: Vec<(String, String)> = Vec::new();
    let mut authority_hints: Vec<String> = Vec::new();
    let mut ta_trust_marks: Vec<(String, String)> = Vec::new(); // (type, id)

    if let Some(ref jwt_str) = entity_jwt
        && let Ok((payload, _)) = get_unverified_payload_header(jwt_str)
    {
        // Extract federation_entity metadata
        if let Some(metadata) = payload.claim("metadata").and_then(|v| v.as_object())
            && let Some(fed) = metadata
                .get("federation_entity")
                .and_then(|v| v.as_object())
        {
            if let Some(name) = fed.get("organization_name").and_then(|v| v.as_str()) {
                ta_name = name.to_string();
            }
            // Collect endpoints
            let endpoint_names = [
                ("federation_fetch_endpoint", "Fetch"),
                ("federation_list_endpoint", "List"),
                ("federation_resolve_endpoint", "Resolve"),
                ("federation_collection_endpoint", "Collection"),
                ("federation_trust_mark_endpoint", "Trust Mark"),
                ("federation_trust_mark_list_endpoint", "Trust Mark List"),
                ("federation_trust_mark_status_endpoint", "Trust Mark Status"),
                ("federation_historical_keys_endpoint", "Historical Keys"),
            ];
            for (key, label) in endpoint_names {
                if let Some(url) = fed.get(key).and_then(|v| v.as_str()) {
                    endpoints.push((label.to_string(), url.to_string()));
                }
            }
        }
        // Extract authority_hints
        if let Some(hints) = payload.claim("authority_hints").and_then(|v| v.as_array()) {
            for h in hints {
                if let Some(s) = h.as_str() {
                    authority_hints.push(s.to_string());
                }
            }
        }
        // Extract trust_marks
        if let Some(tms) = payload.claim("trust_marks").and_then(|v| v.as_array()) {
            for tm in tms {
                if let Some(obj) = tm.as_object() {
                    let tm_id = obj.get("id").and_then(|v| v.as_str()).unwrap_or_default();
                    let tm_type = obj
                        .get("trust_mark_type")
                        .and_then(|v| v.as_str())
                        .unwrap_or(tm_id);
                    ta_trust_marks.push((tm_type.to_string(), tm_id.to_string()));
                }
            }
        }
    }

    // Fetch collection entities
    let collection_entities: Vec<(String, String)> =
        redis::Cmd::hgetall("inmor:collection:entities")
            .query_async::<Vec<(String, String)>>(&mut conn)
            .await
            .unwrap_or_default();

    let last_updated: Option<u64> = redis::Cmd::get("inmor:collection:last_updated")
        .query_async(&mut conn)
        .await
        .ok();

    // Parse collection entries
    struct CollectionEntry {
        entity_id: String,
        entity_types: Vec<String>,
        display_name: Option<String>,
        logo_uri: Option<String>,
    }

    let mut entries: Vec<CollectionEntry> = Vec::new();
    for (_eid, json_str) in &collection_entities {
        if let Ok(resp) = serde_json::from_str::<EntityCollectionResponse>(json_str) {
            let mut display_name = None;
            let mut logo_uri = None;
            if let Some(ref ui) = resp.ui_infos {
                // Try federation_entity first, then any type
                for key in &[
                    "federation_entity",
                    "openid_provider",
                    "openid_relying_party",
                ] {
                    if let Some(info) = ui.get(*key) {
                        if display_name.is_none()
                            && let Some(ref dn) = info.display_name
                            && !dn.is_empty()
                        {
                            display_name = Some(dn.clone());
                        }
                        if logo_uri.is_none()
                            && let Some(ref lu) = info.logo_uri
                            && !lu.is_empty()
                        {
                            logo_uri = Some(lu.clone());
                        }
                    }
                }
            }
            entries.push(CollectionEntry {
                entity_id: resp.entity_id,
                entity_types: resp.entity_types,
                display_name,
                logo_uri,
            });
        }
    }
    entries.sort_by(|a, b| a.entity_id.cmp(&b.entity_id));

    // Separate into categories
    let intermediates: Vec<&CollectionEntry> = entries
        .iter()
        .filter(|e| {
            e.entity_types.contains(&"federation_entity".to_string())
                && !e
                    .entity_types
                    .iter()
                    .any(|t| t == "openid_provider" || t == "openid_relying_party")
        })
        .filter(|e| e.entity_id != app_state.entity_id)
        .collect();
    let providers: Vec<&CollectionEntry> = entries
        .iter()
        .filter(|e| e.entity_types.contains(&"openid_provider".to_string()))
        .collect();
    let relying_parties: Vec<&CollectionEntry> = entries
        .iter()
        .filter(|e| e.entity_types.contains(&"openid_relying_party".to_string()))
        .collect();

    // Fetch direct subordinate entity IDs
    let direct_sub_ids: Vec<String> = redis::Cmd::hkeys("inmor:subordinates:jwt")
        .query_async(&mut conn)
        .await
        .unwrap_or_default();
    let direct_sub_count = direct_sub_ids.len();

    // Build Tera context
    let entity_id = &app_state.entity_id;
    let version = env!("CARGO_PKG_VERSION");

    let display_title = if ta_name.is_empty() {
        entity_id.clone()
    } else {
        ta_name.clone()
    };

    // Sort direct subordinates
    let mut sorted_sub_ids = direct_sub_ids.clone();
    sorted_sub_ids.sort();

    // Build serializable entity data for template
    let to_entry = |e: &&CollectionEntry| -> serde_json::Value {
        let initial = e
            .entity_id
            .trim_start_matches("https://")
            .trim_start_matches("http://")
            .chars()
            .next()
            .unwrap_or('?')
            .to_uppercase()
            .to_string();
        let type_badges: Vec<serde_json::Value> = e
            .entity_types
            .iter()
            .map(|t| {
                let (class, short) = match t.as_str() {
                    "openid_provider" => ("badge-op", "OP"),
                    "openid_relying_party" => ("badge-rp", "RP"),
                    "federation_entity" => ("badge-fe", "FE"),
                    "oauth_authorization_server" => ("badge-other", "AS"),
                    "oauth_client" => ("badge-other", "OC"),
                    "oauth_resource" => ("badge-other", "OR"),
                    other => ("badge-other", other),
                };
                json!({"class": class, "short": short})
            })
            .collect();
        json!({
            "entity_id": e.entity_id,
            "display_name": e.display_name.as_deref().unwrap_or(""),
            "logo_uri": e.logo_uri,
            "initial": initial,
            "type_badges": type_badges,
        })
    };

    let last_updated_ts = last_updated.filter(|&ts| ts > 0);

    let mut ctx = tera::Context::new();
    ctx.insert("display_title", &display_title);
    ctx.insert("entity_id", entity_id);
    ctx.insert("version", version);
    ctx.insert("direct_sub_count", &direct_sub_count);
    ctx.insert("direct_subordinates", &sorted_sub_ids);
    ctx.insert("total_discovered", &entries.len());
    ctx.insert("op_count", &providers.len());
    ctx.insert("rp_count", &relying_parties.len());
    ctx.insert("ia_count", &intermediates.len());
    ctx.insert("endpoints", &endpoints);
    ctx.insert("authority_hints", &authority_hints);
    ctx.insert("trust_marks", &ta_trust_marks);
    ctx.insert(
        "intermediates",
        &intermediates.iter().map(to_entry).collect::<Vec<_>>(),
    );
    ctx.insert(
        "providers",
        &providers.iter().map(to_entry).collect::<Vec<_>>(),
    );
    ctx.insert(
        "relying_parties",
        &relying_parties.iter().map(to_entry).collect::<Vec<_>>(),
    );
    ctx.insert("last_updated_ts", &last_updated_ts);

    let html = TERA
        .render("index.html", &ctx)
        .map_err(error::ErrorInternalServerError)?;

    Ok(HttpResponse::Ok().content_type("text/html").body(html))
}

/// https://openid.net/specs/openid-federation-1_0.html#name-entity-statement
#[get("/.well-known/openid-federation")]
async fn openid_federation(redis: web::Data<redis::Client>) -> actix_web::Result<impl Responder> {
    let mut conn = redis
        .get_connection_manager()
        .await
        .map_err(error::ErrorInternalServerError)?;

    let res = redis::Cmd::get("inmor:entity_id")
        .query_async::<String>(&mut conn)
        .await
        .map_err(error::ErrorInternalServerError)?;

    Ok(HttpResponse::Ok()
        .content_type("application/entity-statement+jwt")
        .body(res))
}

#[derive(Parser, Debug)]
#[command(version(env!("CARGO_PKG_VERSION")), about(env!("CARGO_PKG_DESCRIPTION")))]
struct Cli {
    #[arg(
        short = 'c',
        long = "config",
        value_name = "FILE",
        help = "Configuration file for the server in .toml format"
    )]
    toml_file_path: String,
    #[arg(short, long, default_value_t = 8080, help = "Port to run the server")]
    port: u16,
}

#[actix_web::main]
async fn main() -> io::Result<()> {
    // Install default crypto provider for rustls
    let _ = rustls::crypto::aws_lc_rs::default_provider().install_default();

    let args = Cli::parse();
    let port = args.port;
    let toml_file_path = args.toml_file_path;
    let server_config = ServerConfiguration::from_toml(&toml_file_path).unwrap_or_else(|_| {
        panic!(
            "Failed reading server configuration from {}.",
            &toml_file_path
        )
    });

    // Now the normal web app flow
    //
    //
    env_logger::init_from_env(env_logger::Env::new().default_filter_or("info"));
    let redis =
        redis::Client::open(server_config.redis_uri.as_str()).expect("Failed to connect to Redis");

    let mut federation = Federation {
        entities: Mutex::new(HashMap::new()),
    };

    let fed_app_data = web::Data::new(federation);

    // Check if TLS configuration is available
    let has_tls = server_config.tls_cert.is_some() && server_config.tls_key.is_some();

    let http_server = HttpServer::new(move || {
        //
        let jwks = get_ta_jwks_public_keyset();
        //
        App::new()
            .app_data(web::Data::new(AppState {
                entity_id: server_config.domain.to_string(),
                public_keyset: jwks,
            }))
            .app_data(web::Data::new(redis.clone()))
            .app_data(fed_app_data.clone())
            .service(index)
            .service(openid_federation)
            .service(list_subordinates)
            .service(fetch_subordinates)
            .service(resolve_entity)
            .service(fetch_collections)
            .service(trust_mark_query)
            .service(trust_mark_list)
            .service(trust_mark_status)
            .service(federation_historical_keys)
            .wrap(middleware::NormalizePath::trim())
            .wrap(middleware::Logger::default())
    })
    .workers(2);

    // If TLS is configured, bind HTTPS on the specified port
    if has_tls {
        let tls_cert_path = server_config.tls_cert.as_ref().unwrap();
        let tls_key_path = server_config.tls_key.as_ref().unwrap();

        eprintln!("Loading TLS certificate from: {}", tls_cert_path);
        eprintln!("Loading TLS key from: {}", tls_key_path);

        // Load TLS certificate and key
        let cert_file = &mut io::BufReader::new(fs::File::open(tls_cert_path)?);
        let key_file = &mut io::BufReader::new(fs::File::open(tls_key_path)?);

        let cert_chain: Vec<_> = certs(cert_file)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("Failed to load TLS certificate: {}", e),
                )
            })?;

        let mut keys = pkcs8_private_keys(key_file)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("Failed to load TLS key: {}", e),
                )
            })?;

        if keys.is_empty() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "No private key found in TLS key file",
            ));
        }

        let tls_config = ServerConfig::builder()
            .with_no_client_auth()
            .with_single_cert(
                cert_chain,
                rustls::pki_types::PrivateKeyDer::Pkcs8(keys.remove(0)),
            )
            .map_err(|e| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("Failed to configure TLS: {}", e),
                )
            })?;

        eprintln!("Starting HTTPS server on 0.0.0.0:{}", port);
        http_server
            .bind_rustls_0_23(("0.0.0.0", port), tls_config)?
            .run()
            .await
    } else {
        eprintln!("Starting HTTP server on 0.0.0.0:{}", port);
        http_server.bind(("0.0.0.0", port))?.run().await
    }
}
