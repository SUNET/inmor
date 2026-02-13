use clap::Parser;
use inmor::ServerConfiguration;
use inmor::tree::run_collection_walk;
use std::io;
use std::time::Instant;

#[derive(Parser, Debug)]
#[command(
    name = "inmor-collection",
    version(env!("CARGO_PKG_VERSION")),
    about = "Walks a federation tree and populates Redis with entity collection data"
)]
struct Cli {
    #[arg(
        short = 'c',
        long = "config",
        value_name = "FILE",
        help = "Configuration file for the server in .toml format"
    )]
    toml_file_path: String,

    #[arg(help = "Entity ID of the trust anchor to walk (e.g. https://ta.example.org)")]
    trust_anchor: String,
}

#[tokio::main]
async fn main() -> io::Result<()> {
    env_logger::init_from_env(env_logger::Env::new().default_filter_or("info"));

    let args = Cli::parse();

    let server_config = ServerConfiguration::from_toml(&args.toml_file_path).unwrap_or_else(|_| {
        panic!(
            "Failed reading server configuration from {}.",
            &args.toml_file_path
        )
    });

    eprintln!("Connecting to Redis at {}", &server_config.redis_uri);
    let redis =
        redis::Client::open(server_config.redis_uri.as_str()).expect("Failed to connect to Redis");

    let mut conn = redis
        .get_connection_manager()
        .await
        .expect("Failed to get Redis connection manager");

    eprintln!("Redis connected");

    let start = Instant::now();
    eprintln!("Starting collection walk from {}", &args.trust_anchor);

    match run_collection_walk(&args.trust_anchor, &mut conn).await {
        Ok(count) => {
            let elapsed = start.elapsed();
            eprintln!(
                "Collection walk complete: {} entities discovered in {:.1}s",
                count,
                elapsed.as_secs_f64()
            );
        }
        Err(e) => {
            eprintln!("Collection walk failed: {}", e);
            std::process::exit(1);
        }
    }

    Ok(())
}
