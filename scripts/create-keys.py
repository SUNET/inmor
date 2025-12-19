# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "jwcrypto",
# ]
# ///
import os
import sys

from jwcrypto import jwk

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

for config in key_configs:
    kty = config["kty"]
    alg = config["alg"]

    if kty == "RSA":
        key = jwk.JWK.generate(kty=kty, size=config["size"], use=config["use"], alg=alg)
    elif kty == "EC":
        key = jwk.JWK.generate(kty=kty, crv=config["crv"], use=config["use"], alg=alg)
    elif kty == "OKP":
        key = jwk.JWK.generate(kty=kty, crv=config["crv"], use=config["use"], alg=alg)

    # Set KID as thumbprint
    key.kid = key.thumbprint()
    kid = key.kid

    # Export public key
    public_path = f"publickeys/{kid}.json"
    with open(public_path, "w") as f:
        f.write(key.export_public())

    # Export private key
    private_path = f"privatekeys/{kid}.json"
    with open(private_path, "w") as f:
        f.write(key.export())

    print(f"Generated {alg} key with KID: {kid}")
