from datetime import datetime, timedelta
from typing import Any, Optional

import redis
from django.conf import settings
from jwcrypto import jwt
from jwcrypto.common import json_decode
from pydantic import BaseModel


class TrustMarkRequest(BaseModel):
    entity: str
    tmt_select: str


class TrustMarkTypeRequest(BaseModel):
    type: str


def add_trustmark(
    entity: str,
    trustmarktype: str,
    expiry: int,
    additional_claims: Optional[dict["str", Any]],
    r: redis.Redis,
) -> str:
    """Adds a new TrustMark for a given entity for a given TrustMarkType.

    :args entity: The entity_id to be added
    :args trustmarktype: The TrustMarkType value in JWT
    :args expiry: The JWT will be valid for the number of hours.
    :args r: Redis client instance.

    :returns: JWT as str.
    """
    # Based on https://openid.net/specs/openid-federation-1_0.html#name-trust-marks

    # This is the data we care for now
    sub_data = {"iss": settings.TRUSTMARK_PROVIDER}
    sub_data["sub"] = entity
    now = datetime.now()
    exp = now + timedelta(hours=expiry)
    sub_data["iat"] = now.timestamp()
    sub_data["exp"] = exp.timestamp()
    if additional_claims:
        sub_data.update(additional_claims)
    sub_data["trust_mark_type"] = trustmarktype

    key = settings.SIGNING_PRIVATE_KEY

    # TODO: fix the alg value for other types of keys of TA/I
    token = jwt.JWT(header={"alg": "RS256", "kid": key.kid}, claims=sub_data)
    token.make_signed_token(key)
    token_data = token.serialize()
    # Now we should set it in the redis
    # First, the trustmark for the entity and that trustmarktype
    _ = r.hset(f"inmor:tm:{entity}", trustmarktype, token_data)
    # second, add to the set of trust_mark_type
    _ = r.sadd(f"inmor:tmtype:{trustmarktype}", entity)
    return token_data


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
    jose = jwt.JWT.from_jose_token(token_str)
    data = json_decode(jose.token.objects.get("payload", ""))
    return data.get("exp")
