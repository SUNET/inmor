from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import redis
from django.conf import settings
from pyjosers import jwt
from pydantic import BaseModel

from common.claims import validate_trust_mark_additional_claims
from common.signing import create_signed_jwt
from trustmarks.models import TrustMark


class TrustMarkRequest(BaseModel):
    entity: str
    tmt_select: str


class TrustMarkTypeRequest(BaseModel):
    type: str


def sign_trustmark(
    entity: str,
    trustmarktype: str,
    expiry: int,
    additional_claims: Optional[dict["str", Any]],
) -> str:
    """Sign a trust mark without changing its database or Redis state."""
    additional_claims = validate_trust_mark_additional_claims(additional_claims)

    # Merge extensions first, then set claims that are authoritative for this issuer.
    sub_data = dict(additional_claims or {})
    sub_data["iss"] = settings.TRUSTMARK_PROVIDER
    sub_data["sub"] = entity
    now = datetime.now(UTC)
    exp = now + timedelta(hours=expiry)
    sub_data["iat"] = now
    sub_data["exp"] = exp
    sub_data["trust_mark_type"] = trustmarktype

    key = settings.SIGNING_PRIVATE_KEY
    return create_signed_jwt(sub_data, key, "trust-mark+jwt")


def issue_trustmark(tm: TrustMark, valid_for: int) -> None:
    """Set the signed mark and its expiry on the instance for the caller to save."""
    mark = sign_trustmark(tm.domain, tm.tmt.tmtype, valid_for, tm.additional_claims)
    tm.mark = mark
    tm.expire_at = datetime.fromtimestamp(get_expiry(mark), UTC)


def get_trustmark(entity: str, trustmarktype: str, r: redis.Redis) -> str | None:
    """Get a TrustMark for an entity from redis.

    :args entity: The entity_id to be added
    :args trustmarktype: The TrustMarkType value in JWT
    :args r: Redis client instance.

    :returns: JWT as str.
    """
    token = r.hget(f"inmor:tm:{entity}", trustmarktype)
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return


def get_expiry(token_str: str) -> float:
    """Extracts the expiry time as timestamp from JWT."""
    _header, data = jwt.decode_unverified(token_str)
    return float(data["exp"])
