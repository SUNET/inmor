use std::fs;
use std::io::{self, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use anyhow::{Context, Result, bail};
use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use clap::{Parser, ValueEnum};
use josekit::jwk::Jwk;
use josekit::jwk::KeyPair;
use josekit::jwk::alg::ec::{EcCurve, EcKeyPair};
use josekit::jwk::alg::ed::{EdCurve, EdKeyPair};
use josekit::jwk::alg::rsa::RsaKeyPair;
use sha2::{Digest, Sha256};

#[derive(Parser, Debug)]
#[command(
    name = "inmor-keygeneration",
    version(env!("CARGO_PKG_VERSION")),
    about = "Generates a Trust Anchor signing keypair (private.json + public JWK)"
)]
struct Cli {
    #[arg(
        long = "type",
        value_enum,
        ignore_case = true,
        help = "Key/algorithm type to generate"
    )]
    key_type: KeyType,

    #[arg(
        long = "output",
        value_name = "DIR",
        default_value = ".",
        help = "Directory to write private.json and publickeys/{kid}.json into"
    )]
    output: PathBuf,

    #[arg(long = "force", help = "Overwrite an existing private.json")]
    force: bool,
}

/// Supported signing key types, named after their JWK `alg` value.
#[derive(Copy, Clone, Debug, PartialEq, Eq, ValueEnum)]
enum KeyType {
    #[value(name = "RS256")]
    Rs256,
    #[value(name = "PS256")]
    Ps256,
    #[value(name = "ES256")]
    Es256,
    #[value(name = "ES384")]
    Es384,
    #[value(name = "ES512")]
    Es512,
    #[value(name = "Ed25519")]
    Ed25519,
    #[value(name = "Ed448")]
    Ed448,
}

impl KeyType {
    /// The JWK `alg` value stamped onto the generated key.
    fn alg(self) -> &'static str {
        match self {
            KeyType::Rs256 => "RS256",
            KeyType::Ps256 => "PS256",
            KeyType::Es256 => "ES256",
            KeyType::Es384 => "ES384",
            KeyType::Es512 => "ES512",
            KeyType::Ed25519 => "Ed25519",
            KeyType::Ed448 => "Ed448",
        }
    }
}

/// Generate a fresh keypair and return its `(private_jwk, public_jwk)`.
///
/// The private JWK is a complete key pair (private + public members), matching
/// the existing on-disk convention. RS256 and PS256 share identical RSA key
/// material; only the `alg` stamped on the JWK distinguishes them, so both
/// come from the same RSA generator.
fn generate_keypair(key_type: KeyType) -> Result<(Jwk, Jwk)> {
    let pair: (Jwk, Jwk) = match key_type {
        KeyType::Rs256 | KeyType::Ps256 => {
            let kp = RsaKeyPair::generate(2048).context("RSA key generation failed")?;
            (kp.to_jwk_key_pair(), kp.to_jwk_public_key())
        }
        KeyType::Es256 => {
            let kp =
                EcKeyPair::generate(EcCurve::P256).context("EC P-256 key generation failed")?;
            (kp.to_jwk_key_pair(), kp.to_jwk_public_key())
        }
        KeyType::Es384 => {
            let kp =
                EcKeyPair::generate(EcCurve::P384).context("EC P-384 key generation failed")?;
            (kp.to_jwk_key_pair(), kp.to_jwk_public_key())
        }
        KeyType::Es512 => {
            let kp =
                EcKeyPair::generate(EcCurve::P521).context("EC P-521 key generation failed")?;
            (kp.to_jwk_key_pair(), kp.to_jwk_public_key())
        }
        KeyType::Ed25519 => {
            let kp =
                EdKeyPair::generate(EdCurve::Ed25519).context("Ed25519 key generation failed")?;
            (kp.to_jwk_key_pair(), kp.to_jwk_public_key())
        }
        KeyType::Ed448 => {
            let kp = EdKeyPair::generate(EdCurve::Ed448).context("Ed448 key generation failed")?;
            (kp.to_jwk_key_pair(), kp.to_jwk_public_key())
        }
    };
    Ok(pair)
}

/// Return a complete private JWK that contains every member of the public JWK.
///
/// josekit's `to_jwk_key_pair()` returns full RSA and EC keys, but omits the
/// public `x` member for OKP (Ed) keys. Filling in any missing public member
/// keeps `private.json` a self-contained, RFC-conformant key pair.
fn complete_private_jwk(private: &Jwk, public: &Jwk) -> Result<Jwk> {
    let mut map = private.as_ref().clone();
    for (key, value) in public.as_ref() {
        map.entry(key.clone()).or_insert_with(|| value.clone());
    }
    Jwk::from_map(map).context("failed to assemble complete private JWK")
}

/// Compute the RFC 7638 JWK thumbprint (SHA-256, base64url, no padding).
///
/// josekit does not expose this, so it is built here from the required
/// members in lexicographic order. Those member values are base64url strings
/// (or fixed curve names) with no JSON-escapable characters, so the canonical
/// JSON is assembled directly.
fn jwk_thumbprint(jwk: &Jwk) -> Result<String> {
    let kty = jwk.key_type();
    let canonical = match kty {
        "RSA" => {
            let e = required_member(jwk, "e")?;
            let n = required_member(jwk, "n")?;
            format!(r#"{{"e":"{e}","kty":"RSA","n":"{n}"}}"#)
        }
        "EC" => {
            let crv = required_member(jwk, "crv")?;
            let x = required_member(jwk, "x")?;
            let y = required_member(jwk, "y")?;
            format!(r#"{{"crv":"{crv}","kty":"EC","x":"{x}","y":"{y}"}}"#)
        }
        "OKP" => {
            let crv = required_member(jwk, "crv")?;
            let x = required_member(jwk, "x")?;
            format!(r#"{{"crv":"{crv}","kty":"OKP","x":"{x}"}}"#)
        }
        other => bail!("cannot compute thumbprint for unsupported key type '{other}'"),
    };
    Ok(URL_SAFE_NO_PAD.encode(Sha256::digest(canonical.as_bytes())))
}

/// Read a required string member from a JWK.
fn required_member(jwk: &Jwk, key: &str) -> Result<String> {
    jwk.parameter(key)
        .and_then(|v| v.as_str())
        .map(str::to_owned)
        .with_context(|| format!("generated JWK is missing required member '{key}'"))
}

/// Serialize a JWK to pretty-printed JSON with a trailing newline.
fn jwk_to_json(jwk: &Jwk) -> Result<String> {
    let mut json = serde_json::to_string_pretty(jwk.as_ref())?;
    json.push('\n');
    Ok(json)
}

/// The error shown when `private.json` already exists and `--force` was not given.
fn already_exists_error(path: &Path) -> anyhow::Error {
    anyhow::anyhow!(
        "{} already exists.\n  Re-run with --force to overwrite (this invalidates all \
         entity statements and trust marks already signed by the Trust Anchor).",
        path.display()
    )
}

/// Write `contents` to `path` with an explicit file mode.
///
/// When `overwrite` is false the file is created atomically (`create_new`), so
/// the call fails with `AlreadyExists` instead of clobbering a file that
/// appeared after an earlier existence check — closing the TOCTOU gap. The
/// mode is also reapplied after writing so it is enforced when overwriting an
/// existing file (where `OpenOptions::mode` has no effect).
fn write_file(path: &Path, contents: &str, mode: u32, overwrite: bool) -> io::Result<()> {
    let mut options = fs::OpenOptions::new();
    options.write(true).mode(mode);
    if overwrite {
        options.create(true).truncate(true);
    } else {
        options.create_new(true);
    }
    let mut file = options.open(path)?;
    file.write_all(contents.as_bytes())?;
    fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
    Ok(())
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    let alg = cli.key_type.alg();

    let private_path = cli.output.join("private.json");
    // Fast, friendly check for the common case. `write_file` below still uses
    // `create_new`, so a file appearing after this check cannot be clobbered.
    if private_path.exists() && !cli.force {
        return Err(already_exists_error(&private_path));
    }

    let (private_pair, mut public_jwk) = generate_keypair(cli.key_type)?;
    let mut private_jwk = complete_private_jwk(&private_pair, &public_jwk)?;
    let kid = jwk_thumbprint(&public_jwk)?;

    for jwk in [&mut private_jwk, &mut public_jwk] {
        jwk.set_key_use("sig");
        jwk.set_algorithm(alg);
        jwk.set_key_id(kid.as_str());
    }

    let publickeys_dir = cli.output.join("publickeys");
    fs::create_dir_all(&cli.output)
        .with_context(|| format!("failed to create {}", cli.output.display()))?;
    fs::create_dir_all(&publickeys_dir)
        .with_context(|| format!("failed to create {}", publickeys_dir.display()))?;

    let public_path = publickeys_dir.join(format!("{kid}.json"));

    // Write the public key first: it is content-addressed by `kid` and safe to
    // (re)write, so if the private-key write fails the state stays recoverable
    // (no private.json without its public half).
    write_file(&public_path, &jwk_to_json(&public_jwk)?, 0o644, true)
        .with_context(|| format!("failed to write {}", public_path.display()))?;

    if let Err(err) = write_file(&private_path, &jwk_to_json(&private_jwk)?, 0o600, cli.force) {
        return Err(if err.kind() == io::ErrorKind::AlreadyExists {
            already_exists_error(&private_path)
        } else {
            anyhow::Error::new(err).context(format!("failed to write {}", private_path.display()))
        });
    }

    println!("Generated {alg} key with KID: {kid}");
    println!("  private key: {}", private_path.display());
    println!("  public key:  {}", public_path.display());
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("error: {err:#}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use josekit::jws::{
        self, ES256, ES384, ES512, EdDSA, JwsHeader, JwsSigner, JwsVerifier, PS256, RS256,
    };

    /// RFC 7638 Section 3.1 worked example.
    #[test]
    fn rfc7638_thumbprint_known_answer() {
        let jwk_json = r#"{
            "kty":"RSA",
            "n":"0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
            "e":"AQAB",
            "alg":"RS256",
            "kid":"2011-04-29"
        }"#;
        let jwk = Jwk::from_bytes(jwk_json.as_bytes()).expect("valid JWK");
        assert_eq!(
            jwk_thumbprint(&jwk).expect("thumbprint"),
            "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs"
        );
    }

    /// Generate a key, stamp it, and return both JWKs the way `run()` does.
    fn generate_stamped(key_type: KeyType) -> (Jwk, Jwk, String) {
        let (private_pair, mut public_jwk) = generate_keypair(key_type).expect("generation");
        let mut private_jwk =
            complete_private_jwk(&private_pair, &public_jwk).expect("complete private JWK");
        let kid = jwk_thumbprint(&public_jwk).expect("thumbprint");
        for jwk in [&mut private_jwk, &mut public_jwk] {
            jwk.set_key_use("sig");
            jwk.set_algorithm(key_type.alg());
            jwk.set_key_id(kid.as_str());
        }
        (private_jwk, public_jwk, kid)
    }

    fn all_types() -> [KeyType; 7] {
        [
            KeyType::Rs256,
            KeyType::Ps256,
            KeyType::Es256,
            KeyType::Es384,
            KeyType::Es512,
            KeyType::Ed25519,
            KeyType::Ed448,
        ]
    }

    #[test]
    fn generated_keys_have_expected_fields() {
        for key_type in all_types() {
            let (private_jwk, public_jwk, kid) = generate_stamped(key_type);

            for jwk in [&private_jwk, &public_jwk] {
                assert_eq!(jwk.algorithm(), Some(key_type.alg()), "{key_type:?} alg");
                assert_eq!(jwk.key_use(), Some("sig"), "{key_type:?} use");
                assert_eq!(jwk.key_id(), Some(kid.as_str()), "{key_type:?} kid");
            }

            // The kid must equal the thumbprint of the public key.
            assert_eq!(
                jwk_thumbprint(&public_jwk).unwrap(),
                kid,
                "{key_type:?} kid"
            );

            // Private material is present in the private JWK only.
            assert!(
                private_jwk.parameter("d").is_some(),
                "{key_type:?} private key missing 'd'"
            );
            assert!(
                public_jwk.parameter("d").is_none(),
                "{key_type:?} public key leaked 'd'"
            );

            // The private JWK is a complete superset of the public JWK.
            for member in ["kty", "n", "e", "crv", "x", "y"] {
                if public_jwk.parameter(member).is_some() {
                    assert_eq!(
                        private_jwk.parameter(member),
                        public_jwk.parameter(member),
                        "{key_type:?} private key missing public member '{member}'"
                    );
                }
            }
        }
    }

    /// Mirror `create_signed_jwt` in src/lib.rs: inmor stores Ed keys with
    /// `alg` "Ed25519"/"Ed448", but josekit's EdDSA signer requires "EdDSA".
    fn normalize_for_josekit(jwk: &Jwk) -> Jwk {
        match jwk.algorithm() {
            Some("Ed25519") | Some("Ed448") => {
                let mut map = jwk.as_ref().clone();
                map.insert("alg".to_string(), serde_json::json!("EdDSA"));
                Jwk::from_map(map).expect("valid JWK")
            }
            _ => jwk.clone(),
        }
    }

    fn signer_for(key_type: KeyType, jwk: &Jwk) -> Box<dyn JwsSigner> {
        let jwk = normalize_for_josekit(jwk);
        match key_type {
            KeyType::Rs256 => Box::new(RS256.signer_from_jwk(&jwk).unwrap()),
            KeyType::Ps256 => Box::new(PS256.signer_from_jwk(&jwk).unwrap()),
            KeyType::Es256 => Box::new(ES256.signer_from_jwk(&jwk).unwrap()),
            KeyType::Es384 => Box::new(ES384.signer_from_jwk(&jwk).unwrap()),
            KeyType::Es512 => Box::new(ES512.signer_from_jwk(&jwk).unwrap()),
            KeyType::Ed25519 | KeyType::Ed448 => Box::new(EdDSA.signer_from_jwk(&jwk).unwrap()),
        }
    }

    fn verifier_for(key_type: KeyType, jwk: &Jwk) -> Box<dyn JwsVerifier> {
        let jwk = normalize_for_josekit(jwk);
        match key_type {
            KeyType::Rs256 => Box::new(RS256.verifier_from_jwk(&jwk).unwrap()),
            KeyType::Ps256 => Box::new(PS256.verifier_from_jwk(&jwk).unwrap()),
            KeyType::Es256 => Box::new(ES256.verifier_from_jwk(&jwk).unwrap()),
            KeyType::Es384 => Box::new(ES384.verifier_from_jwk(&jwk).unwrap()),
            KeyType::Es512 => Box::new(ES512.verifier_from_jwk(&jwk).unwrap()),
            KeyType::Ed25519 | KeyType::Ed448 => Box::new(EdDSA.verifier_from_jwk(&jwk).unwrap()),
        }
    }

    /// Every generated keypair must sign and verify a round-trip, proving the
    /// key works for the Trust Anchor's JWT signing path.
    #[test]
    fn generated_keys_sign_and_verify() {
        let payload = b"inmor-keygeneration round-trip";
        for key_type in all_types() {
            let (private_jwk, public_jwk, _) = generate_stamped(key_type);
            let signer = signer_for(key_type, &private_jwk);
            let verifier = verifier_for(key_type, &public_jwk);

            let compact = jws::serialize_compact(payload, &JwsHeader::new(), &*signer)
                .unwrap_or_else(|e| panic!("{key_type:?} sign failed: {e}"));
            let (out, _) = jws::deserialize_compact(&compact, &*verifier)
                .unwrap_or_else(|e| panic!("{key_type:?} verify failed: {e}"));
            assert_eq!(out, payload, "{key_type:?} round-trip payload mismatch");
        }
    }

    /// `write_file` must not clobber an existing file unless overwrite is set,
    /// and must enforce the requested mode.
    #[test]
    fn write_file_respects_overwrite_and_mode() {
        let dir = std::env::temp_dir().join(format!("inmor-keygen-write-{}", std::process::id()));
        fs::create_dir_all(&dir).expect("temp dir");
        let path = dir.join("private.json");
        let _ = fs::remove_file(&path);

        // First write creates the file.
        write_file(&path, "first", 0o600, false).expect("initial write");
        assert_eq!(fs::read_to_string(&path).unwrap(), "first");

        // Without overwrite a second write fails atomically and leaves the
        // original contents intact (no truncation).
        let err = write_file(&path, "second", 0o600, false).expect_err("must refuse overwrite");
        assert_eq!(err.kind(), io::ErrorKind::AlreadyExists);
        assert_eq!(fs::read_to_string(&path).unwrap(), "first");

        // With overwrite the file is replaced and the mode is reapplied.
        write_file(&path, "third", 0o600, true).expect("force overwrite");
        assert_eq!(fs::read_to_string(&path).unwrap(), "third");
        let mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);

        fs::remove_dir_all(&dir).ok();
    }
}
