"""Generic JWT signing utilities for different key types and algorithms."""

from typing import Any

from jwcrypto import jwt
from jwcrypto.jwk import JWK


def create_signed_jwt(
    claims: dict[str, Any],
    key: JWK,
    token_type: str | None = None,
) -> str:
    """Create a signed JWT with the given claims and key.

    This function supports signing with different key types (RSA, EC, OKP) and
    algorithms (RS256, PS256, ES256, ES384, ES512, Ed25519, Ed448).

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

    # jwcrypto uses "EdDSA" as the algorithm name for both Ed25519 and Ed448
    # Map the RFC 9864 fully-specified algorithm names to jwcrypto's EdDSA
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
