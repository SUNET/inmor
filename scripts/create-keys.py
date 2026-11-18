# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyjosers>=0.4.1",
# ]
# ///
import argparse
import os

from pyjosers import jwk

PQC_ALGORITHMS = (
    "ML-DSA-44",
    "ML-DSA-65",
    "ML-DSA-87",
    "ML-DSA-44-ES256",
    "ML-DSA-65-ES256",
    "ML-DSA-87-ES384",
    "ML-DSA-44-Ed25519",
    "ML-DSA-65-Ed25519",
    "ML-DSA-87-Ed448",
)

parser = argparse.ArgumentParser(description="Generate development signing keypairs")
parser.add_argument("--pqc", choices=(*PQC_ALGORITHMS, "all"))
args = parser.parse_args()

# Ensure directories exist
os.makedirs("publickeys", exist_ok=True)
os.makedirs("privatekeys", exist_ok=True)

# Define all key types to generate based on RFC 9864 Section 2
# https://www.rfc-editor.org/rfc/rfc9864.html#section-2
key_configs = [
    # RSA keys (already exists, but we'll keep it for backwards compatibility)
    {"kty": "RSA", "size": 2048, "use": "sig", "alg": "RS256"},
    {"kty": "RSA", "size": 2048, "use": "sig", "alg": "PS256"},
    # EC keys - P-256, P-384, P-521
    {"kty": "EC", "crv": "P-256", "use": "sig", "alg": "ES256"},
    {"kty": "EC", "crv": "P-384", "use": "sig", "alg": "ES384"},
    {"kty": "EC", "crv": "P-521", "use": "sig", "alg": "ES512"},
    # Edwards curve keys - Ed25519, Ed448
    {"kty": "OKP", "crv": "Ed25519", "use": "sig", "alg": "Ed25519"},
    {"kty": "OKP", "crv": "Ed448", "use": "sig", "alg": "Ed448"},
]

if args.pqc:
    algorithms = PQC_ALGORITHMS if args.pqc == "all" else [args.pqc]
    key_configs = [{"kty": "AKP", "use": "sig", "alg": alg} for alg in algorithms]

for config in key_configs:
    alg = config["alg"]
    key = jwk.JWK.generate(**config)

    # Set KID as thumbprint
    key.kid = key.thumbprint()
    kid = key.kid

    # Export public key
    public_path = f"publickeys/{kid}.json"
    with open(public_path, "w") as f:
        f.write(key.export_public())

    # Export private key
    private_path = f"privatekeys/{kid}.json"
    with os.fdopen(os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        f.write(key.export())

    print(f"Generated {alg} key with KID: {kid}")
