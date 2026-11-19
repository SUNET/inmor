"""Generic JWT signing utilities for different key types and algorithms."""

from typing import Any

from pyjosers import jwt
from pyjosers.jwk import JWK, JWKSet


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
FEDERATION_ALGORITHMS = (
    "RS256",
    "PS256",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
    "Ed25519",
    "Ed448",
    *PQC_ALGORITHMS,
)


def verify_federation_jwt(token: str, keys: JWKSet) -> jwt.JWT:
    """Verify a federation JWT under the Trust Anchor algorithm policy."""
    return jwt.JWT(jwt=token, key=keys, algs=list(FEDERATION_ALGORITHMS))


def create_signed_jwt(
    claims: dict[str, Any],
    key: JWK,
    token_type: str | None = None,
) -> str:
    """Create a signed JWT with the given claims and key.

    This function supports signing with RSA, EC, OKP and AKP federation keys.

    :param claims: Dictionary of JWT claims
    :param key: JWK private key to sign with
    :param token_type: Optional JWT type (e.g., "entity-statement+jwt")
    :return: Serialized signed JWT string
    """
    # Get the algorithm from the key
    alg = key.get("alg")
    if not alg:
        # Fallback to RS256 if no algorithm is specified
        alg = "RS256"

    # Keys are stored with the RFC 9864 fully specified names, but the JWS
    # header keeps the widely deployed "EdDSA" identifier. pyjosers accepts
    # "EdDSA" for a key pinned to the matching Edwards curve.
    if alg in ("Ed25519", "Ed448"):
        alg = "EdDSA"

    # Build the header
    header = {"alg": alg, "kid": key.get("kid") or key.thumbprint()}
    if token_type:
        header["typ"] = token_type

    # Create and sign the token
    token = jwt.JWT(header=header, claims=claims)
    token.make_signed_token(key)
    return token.serialize()
