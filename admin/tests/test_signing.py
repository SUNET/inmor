"""Tests for generic JWT signing with different key types."""

import json
import os
from datetime import datetime, timedelta

import pytest
from django.conf import settings
from jwcrypto import jwk, jwt
from jwcrypto.jwk import JWK

from common.signing import create_signed_jwt


class TestGenericSigning:
    """Test signing with different key types and algorithms."""

    @pytest.fixture
    def all_private_keys(self):
        """Load all private keys from the privatekeys directory."""
        keys = []
        privatekeys_dir = "./privatekeys"

        for filename in os.listdir(privatekeys_dir):
            if filename.endswith(".json"):
                key_path = os.path.join(privatekeys_dir, filename)
                key = JWK.from_json(open(key_path).read())
                keys.append(key)

        return keys

    @pytest.fixture
    def sample_claims(self):
        """Sample JWT claims for testing."""
        now = datetime.now()
        exp = now + timedelta(hours=1)

        return {
            "iss": "http://localhost:8080",
            "sub": "http://example.com",
            "iat": now.timestamp(),
            "exp": exp.timestamp(),
            "test_claim": "test_value",
        }

    def test_sign_with_all_key_types(self, all_private_keys, sample_claims):
        """Test signing with all available key types."""
        assert len(all_private_keys) > 0, "No private keys found in ./privatekeys"

        for key in all_private_keys:
            alg = key.get("alg")
            kid = key.kid

            # Create signed JWT
            token_str = create_signed_jwt(sample_claims, key)

            # Verify it's a valid JWT string
            assert isinstance(token_str, str)
            assert token_str.count(".") == 2, f"Invalid JWT format for key {kid} ({alg})"

            print(f"\n✓ Successfully signed with {alg} (kid: {kid})")

    def test_verify_signed_jwt_with_all_key_types(self, all_private_keys, sample_claims):
        """Test that signed JWTs can be verified with their corresponding public keys."""
        for private_key in all_private_keys:
            alg = private_key.get("alg")
            kid = private_key.kid

            # Create signed JWT
            token_str = create_signed_jwt(sample_claims, private_key)

            # Get the corresponding public key
            public_key = JWK.from_json(private_key.export_public())

            # Verify the JWT using jwcrypto
            token = jwt.JWT(jwt=token_str, key=public_key)

            # Decode and verify claims
            claims = json.loads(token.claims)
            assert claims["iss"] == sample_claims["iss"]
            assert claims["sub"] == sample_claims["sub"]
            assert claims["test_claim"] == sample_claims["test_claim"]

            print(f"\n✓ Successfully verified JWT signed with {alg} (kid: {kid})")

    def test_sign_with_token_type(self, all_private_keys, sample_claims):
        """Test signing with custom token type in header."""
        for private_key in all_private_keys:
            alg = private_key.get("alg")

            # Create signed JWT with custom type
            token_str = create_signed_jwt(
                sample_claims, private_key, token_type="entity-statement+jwt"
            )

            # Decode header to verify token type
            header_part = token_str.split(".")[0]
            import base64

            # Add padding if needed
            header_part += "=" * (4 - len(header_part) % 4)
            header = json.loads(base64.urlsafe_b64decode(header_part))

            assert header["typ"] == "entity-statement+jwt"
            # jwcrypto uses EdDSA for both Ed25519 and Ed448
            expected_alg = "EdDSA" if alg in ("Ed25519", "Ed448") else alg
            assert header["alg"] == expected_alg
            assert "kid" in header

            print(f"\n✓ Successfully added token type for {alg}")

    def test_sign_entity_statement(self, all_private_keys):
        """Test signing an entity statement with all key types."""
        for private_key in all_private_keys:
            alg = private_key.get("alg")
            kid = private_key.kid

            # Create entity statement claims
            now = datetime.now()
            exp = now + timedelta(hours=24)

            sub_data = {
                "iss": settings.TA_DOMAIN,
                "sub": settings.TA_DOMAIN,
                "iat": now.timestamp(),
                "exp": exp.timestamp(),
                "metadata": {
                    "federation_entity": {
                        "federation_fetch_endpoint": f"{settings.TA_DOMAIN}/fetch",
                        "federation_list_endpoint": f"{settings.TA_DOMAIN}/list",
                    }
                },
            }

            # Sign the entity statement
            token_str = create_signed_jwt(sub_data, private_key, token_type="entity-statement+jwt")

            # Verify it's valid
            public_key = JWK.from_json(private_key.export_public())
            token = jwt.JWT(jwt=token_str, key=public_key)
            claims = json.loads(token.claims)

            assert claims["iss"] == settings.TA_DOMAIN
            assert claims["sub"] == settings.TA_DOMAIN
            assert "metadata" in claims

            print(f"\n✓ Entity statement signed and verified with {alg} (kid: {kid})")

    def test_algorithms_present(self, all_private_keys):
        """Verify we have all expected algorithm types."""
        algorithms = {key.get("alg") for key in all_private_keys}

        # Check we have at least these algorithms
        expected_algs = {"RS256", "PS256", "ES256", "ES384", "ES512", "Ed25519", "Ed448"}

        for alg in expected_algs:
            assert alg in algorithms, f"Missing key for algorithm: {alg}"

        print(f"\n✓ All expected algorithms present: {sorted(algorithms)}")
