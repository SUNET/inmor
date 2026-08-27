from collections.abc import Collection
from typing import Any


SIGNED_STATEMENT_PROTECTED_CLAIMS = frozenset({"iss", "sub", "exp", "iat"})
TRUST_MARK_PROTECTED_CLAIMS = SIGNED_STATEMENT_PROTECTED_CLAIMS | {"trust_mark_type"}
SUBORDINATE_PROTECTED_CLAIMS = SIGNED_STATEMENT_PROTECTED_CLAIMS | {
    "jwks",
    "metadata",
    "metadata_policy",
}


def validate_additional_claims(
    additional_claims: Any,
    protected_claims: Collection[str],
) -> dict[str, Any] | None:
    """Reject additional claims that could replace authoritative signed claims."""
    if additional_claims is None:
        return None
    if not isinstance(additional_claims, dict):
        raise ValueError("additional_claims must be a JSON object")

    conflicts = sorted(additional_claims.keys() & set(protected_claims))
    if conflicts:
        names = ", ".join(conflicts)
        raise ValueError(f"additional_claims contains protected claims: {names}")
    return additional_claims


def validate_trust_mark_additional_claims(
    additional_claims: Any,
) -> dict[str, Any] | None:
    """Validate extension claims for a Trust Mark."""
    return validate_additional_claims(additional_claims, TRUST_MARK_PROTECTED_CLAIMS)


def validate_subordinate_additional_claims(
    additional_claims: Any,
) -> dict[str, Any] | None:
    """Validate extension claims for a subordinate statement."""
    return validate_additional_claims(additional_claims, SUBORDINATE_PROTECTED_CLAIMS)
