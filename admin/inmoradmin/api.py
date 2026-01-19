import json
import os
from datetime import datetime, timedelta
from typing import Annotated, Any

import httpx
import pytz
from django.conf import settings
from django.http import HttpRequest
from django_redis import get_redis_connection
from ninja import NinjaAPI, Router, Schema
from ninja.pagination import LimitOffsetPagination, paginate
from pydantic import BaseModel, BeforeValidator, Field
from redis.client import Redis

from common.signing import create_signed_jwt
from entities.lib import (
    apply_server_policy,
    create_server_statement,
    create_subordinate_statement,
    fetch_entity_configuration,
    fetch_payload,
    merge_our_policy_ontop_subpolicy,
    update_redis_with_subordinate,
)
from entities.models import Subordinate
from trustmarks.lib import add_trustmark, get_expiry
from trustmarks.models import TrustMark, TrustMarkType

from .auth import auth_router, combined_auth

api = NinjaAPI(
    title="Inmor Admin API",
    version="0.2.0",
    description="Admin API for managing Trust Anchor entities, subordinates, and trust marks.",
)

# Protected router - requires authentication (session or API key)
router = Router(auth=combined_auth)

DEFAULTS: dict[str, dict[str, Any]] = settings.TA_DEFAULTS


class TrustMarkTypeGetSchema(Schema):
    tmtype: Annotated[str, Field(description="URL to describe the Trust Mark Type.")]


class TrustMarkTypeSchema(Schema):
    tmtype: Annotated[str, Field(description="URL to describe the Trust Mark Type.")]
    autorenew: Annotated[
        bool,
        Field(description="If this TrustMarkType based TrustMarks will be autorenewed or not."),
    ] = DEFAULTS["trustmarktype"]["autorenew"]
    valid_for: Annotated[
        int, Field(description="How long the TrustMark from this type will be valid in hours.")
    ] = DEFAULTS["trustmarktype"]["valid_for"]
    renewal_time: Annotated[int, Field(description="Time after a TrustMark should be renewed.")] = (
        DEFAULTS["trustmarktype"]["renewal_time"]
    )
    active: Annotated[bool, Field(description="If the TrustMarkType is active.")] = DEFAULTS[
        "trustmarktype"
    ]["active"]


class TrustMarkTypeOutSchema(Schema):
    id: int
    tmtype: Annotated[str, Field(description="URL to describe the Trust Mark Type.")]
    autorenew: Annotated[
        bool,
        Field(description="If this TrustMarkType based TrustMarks will be autorenewed or not."),
    ]
    valid_for: Annotated[
        int, Field(description="How long the TrustMark from this type will be valid in hours.")
    ]
    renewal_time: Annotated[int, Field(description="Time after a TrustMark should be renewed.")]

    active: Annotated[bool, Field(description="If the TrustMarkType is active.")]


class TrustMarkTypeUpdateSchema(Schema):
    autorenew: Annotated[
        bool | None,
        Field(description="If this TrustMarkType based TrustMarks will be autorenewed or not."),
    ] = None
    valid_for: Annotated[
        int | None,
        Field(description="How long the TrustMark from this type will be valid in hours."),
    ] = None
    renewal_time: Annotated[
        int | None, Field(description="Time after a TrustMark should be renewed.")
    ] = None

    active: Annotated[bool | None, Field(description="If the TrustMarkType is active.")] = None


class TrustMarkSchema(Schema):
    tmt: int
    domain: str
    autorenew: bool | None = None
    valid_for: int | None = None
    renewal_time: int | None = None
    active: bool | None = None
    additional_claims: dict[str, Any] | None = None


class TrustMarkOutSchema(Schema):
    id: int
    tmt_id: Annotated[int, Field(description="Trust Mark Type ID.")]
    domain: Annotated[str, Field(description="Domain/entity_id the TrustMark was generated for.")]
    expire_at: Annotated[
        datetime, Field(description="Expiry date/time for the current TrustMark JWT.")
    ]
    autorenew: Annotated[
        bool | None,
        Field(description="If this TrustMarkType based TrustMarks will be autorenewed or not."),
    ] = None
    valid_for: Annotated[
        int | None,
        Field(description="How long the TrustMark from this type will be valid in hours."),
    ] = None
    renewal_time: Annotated[
        int | None, Field(description="Time after a TrustMark should be renewed.")
    ] = None
    active: Annotated[bool | None, Field(description="If the TrustMarkType is active.")] = None
    mark: Annotated[str | None, Field(description="The TrustMark JWT.")] = None
    additional_claims: Annotated[
        dict[str, Any] | None, Field(description="Additional claims for the TrustMark JWT.")
    ] = None


class TrustMarkUpdateSchema(Schema):
    autorenew: Annotated[
        bool | None,
        Field(description="If this TrustMarkType based TrustMarks will be autorenewed or not."),
    ] = None
    active: Annotated[bool | None, Field(description="If the TrustMarkType is active.")] = None
    additional_claims: Annotated[
        dict[str, Any] | None, Field(description="Current additional claims for the TrustMark.")
    ] = None


class TrustMarkListSchema(Schema):
    domain: Annotated[str, Field(description="Domain/entity_id the TrustMark was generated for.")]


class JWKSType(BaseModel):
    keys: Annotated[list[dict[str, Any]], Field(min_length=1)]


class EntityStatement(BaseModel):
    entity_statement: Annotated[str, Field(description="The entity statement as JWT.")]


# We need to deserialize from DB
# class MyJWKSType(BaseModel):
# keys: Annotated[
# list[dict[str, Any]],
# BeforeValidator(lambda v: json.loads(v)),
# Field(min_length=1),
# ]


def process_keys_fromdb(v: str | None) -> dict[str, Any]:
    "For the InternalJWKS below"
    if v:
        return json.loads(v)
    return {}


MyDict = Annotated[dict[str, Any], BeforeValidator(lambda v: json.loads(v))]
InternalJWKS = Annotated[dict[str, Any], BeforeValidator(lambda v: process_keys_fromdb(v))]


class EntityTypeSchema(Schema):
    entityid: str
    metadata: dict[Any, Any]
    forced_metadata: dict[Any, Any]
    jwks: dict[Any, Any]
    required_trustmarks: str | None = None
    valid_for: int | None = None
    autorenew: bool | None = True
    active: bool | None = True
    additional_claims: Annotated[
        dict[str, Any] | None,
        Field(description="Additional claims for an Entity which shows in subordinate statement."),
    ] = None


class EntityTypeUpdateSchema(Schema):
    metadata: dict[Any, Any]
    forced_metadata: dict[Any, Any]
    jwks: dict[Any, Any]
    required_trustmarks: str | None = None
    valid_for: int | None = None
    autorenew: bool | None = True
    active: bool | None = True
    additional_claims: Annotated[
        dict[str, Any] | None,
        Field(description="Additional claims for an Entity which shows in subordinate statement."),
    ] = None


class EntityOutSchema(Schema):
    id: int = 0
    entityid: str
    metadata: MyDict
    forced_metadata: MyDict
    jwks: InternalJWKS
    required_trustmarks: str | None = None
    valid_for: int | None = None
    expire_at: datetime | None = None
    autorenew: bool | None = None
    active: bool | None = None
    additional_claims: Annotated[
        dict[str, Any] | None,
        Field(description="Additional claims for an Entity which shows in subordinate statement."),
    ] = None

    @staticmethod
    def resolve_expire_at(obj):
        """Calculate expiration date from added + valid_for."""
        if obj.added and obj.valid_for:
            return obj.added + timedelta(hours=obj.valid_for)
        return None


class Message(Schema):
    message: str
    id: int = 0


# API for TrustMarkTypes


@router.post(
    "/trustmarktypes",
    response={201: TrustMarkTypeOutSchema, 403: TrustMarkTypeOutSchema, 500: Message},
    tags=["TrustMarkType"],
)
def create_trust_mark_type(request: HttpRequest, data: TrustMarkTypeSchema):
    """Creates a new trust_mark_type"""
    try:
        tmt, created = TrustMarkType.objects.get_or_create(
            tmtype=data.tmtype,
            autorenew=data.autorenew,
            valid_for=data.valid_for,
            renewal_time=data.renewal_time,
            active=data.active,
        )
        if created:
            return 201, tmt
        else:
            return 403, tmt
    except Exception as e:
        print(e)
        return 500, {"message": "Error while creating a new TrustMarkType"}


@router.get("/trustmarktypes", response=list[TrustMarkTypeOutSchema], tags=["TrustMarkType"])
@paginate(LimitOffsetPagination)
def list_trust_mark_type(
    request: HttpRequest,
):
    """Lists all existing TrustMarkType(s) from database."""
    return TrustMarkType.objects.all()


@router.get(
    "/trustmarktypes/{int:tmtid}",
    response={200: TrustMarkTypeOutSchema, 404: Message, 500: Message},
    tags=["TrustMarkType"],
)
def get_trustmarktype_byid(request: HttpRequest, tmtid: int):
    """Gets a TrustMarkType"""
    try:
        tmt = TrustMarkType.objects.get(id=tmtid)
        return tmt
    except TrustMarkType.DoesNotExist:
        return 404, {"message": "TrustMarkType could not be found.", "id": tmtid}
    except Exception as e:
        print(e)
        return 500, {"message": "Failed to get TrustMarkType.", "id": tmtid}


@router.get(
    "/trustmarktypes/",
    response={200: TrustMarkTypeOutSchema, 404: Message, 500: Message},
    tags=["TrustMarkType"],
)
def get_trustmarktype_bytype(request: HttpRequest, data: TrustMarkTypeGetSchema):
    """Gets a TrustMarkType"""
    try:
        tmt = TrustMarkType.objects.get(tmtype=data.tmtype)
        return tmt
    except TrustMarkType.DoesNotExist:
        return 404, {"message": "TrustMarkType could not be found."}
    except Exception as e:
        print(e)
        return 500, {"message": "Failed to get TrustMarkType."}


@router.put(
    "/trustmarktypes/{int:tmtid}",
    response={200: TrustMarkTypeOutSchema, 404: Message, 500: Message},
    tags=["TrustMarkType"],
)
def update_trust_mark_type(request: HttpRequest, tmtid: int, data: TrustMarkTypeUpdateSchema):
    """Updates TrustMarkType"""
    try:
        updated = False
        tmt = TrustMarkType.objects.get(id=tmtid)
        if data.active is not None:
            tmt.active = data.active
            updated = True
        if data.autorenew is not None:
            tmt.autorenew = data.autorenew
            updated = True
        if data.valid_for is not None:
            tmt.valid_for = data.valid_for
            updated = True
        if data.renewal_time is not None:
            tmt.renewal_time = data.renewal_time
            updated = True
        # Now save if only updated
        if updated:
            tmt.save()
        return tmt
    except TrustMarkType.DoesNotExist:
        return 404, {"message": "TrustMarkType could not be found.", "id": tmtid}
    except Exception as e:
        print(e)
        return 500, {"message": "Failed to update TrustMarkType.", "id": tmtid}


# API for TrustMarks


@router.post(
    "/trustmarks",
    response={201: TrustMarkOutSchema, 403: TrustMarkOutSchema, 404: Message, 500: Message},
    tags=["TrustMarks"],
)
def create_trust_mark(request: HttpRequest, data: TrustMarkSchema):
    """Creates a new TrustMark for a given domain and TrustMarkType ID."""
    # First get the TrustMarkType
    try:
        tmt = TrustMarkType.objects.get(id=data.tmt)
    except TrustMarkType.DoesNotExist:
        return 404, {"message": "TrustMarkType could not be found.", "id": data.tmt}

    # Now fill in with defaults from TrustMarkType if not given.
    if data.autorenew is None:
        data.autorenew = tmt.autorenew
    if data.active is None:
        data.active = tmt.active
    # valid_for and renewal_time can not be greater than TrustMarkType default.
    if data.valid_for is None:
        data.valid_for = tmt.valid_for
    else:
        # Make sure it is not greater
        if data.valid_for > tmt.valid_for:
            # Oops, we can not allow that.
            return 400, {
                "message": "valid_for is greater than allowed for the given TrustMarkType.",
                "id": data.tmt,
            }
        # All good if we reach here.
    if data.renewal_time is None:
        data.renewal_time = tmt.renewal_time
    else:
        # Make sure it is not greater
        if data.renewal_time > tmt.renewal_time:
            # Oops, we can not allow that.
            return 400, {
                "message": "renewal_time is greater than allowed for the given TrustMarkType.",
                "id": data.tmt,
            }
    try:
        # Task 1: First check if a TrustMark for the given domain and TrustMarkType exists.
        try:
            tm = TrustMark.objects.get(tmt=tmt, domain=data.domain)
            # TrustMark already exists, return 403
            return 403, tm
        except TrustMark.DoesNotExist:
            # Task 2: TrustMark does not exist, create a new TrustMark entry in DB.
            tm = TrustMark.objects.create(
                tmt=tmt,
                domain=data.domain,
                autorenew=data.autorenew,
                valid_for=data.valid_for,
                renewal_time=data.renewal_time,
                active=data.active,
                additional_claims=data.additional_claims,
            )
            con: Redis = get_redis_connection("default")
            # Now we should create the signed JWT and store in redis
            mark = add_trustmark(tm.domain, tmt.tmtype, tm.valid_for, tm.additional_claims, con)
            # Adds the newly created JWT in the response
            tm.mark = mark
            expiry = datetime.fromtimestamp(get_expiry(mark), pytz.utc)
            tm.expire_at = expiry
            tm.save()
            return 201, tm
    except Exception as e:
        print(e)
        return 500, {"message": "Error while creating a new TrustMark."}


@router.post(
    "/trustmarks/list",
    response={200: list[TrustMarkOutSchema], 403: TrustMarkOutSchema, 404: Message, 500: Message},
    tags=["TrustMarks"],
)
@paginate(LimitOffsetPagination)
def get_trustmark_list_perdomain(request: HttpRequest, data: TrustMarkListSchema):
    """Returns a list of existing TrustMarks for a given domain."""
    if data.domain:
        return TrustMark.objects.filter(domain=data.domain)
    return TrustMark.objects.all()


@router.get(
    "/trustmarks",
    response={200: list[TrustMarkOutSchema], 403: TrustMarkOutSchema, 404: Message, 500: Message},
    tags=["TrustMarks"],
)
@paginate(LimitOffsetPagination)
def get_trustmark_list(request: HttpRequest):
    """Returns a list of existing TrustMarks."""
    return TrustMark.objects.all()


@router.post(
    "/trustmarks/{int:tmid}/renew",
    response={200: TrustMarkOutSchema, 404: Message, 500: Message},
    tags=["TrustMarks"],
)
def renew_trustmark(request: HttpRequest, tmid: int):
    """Renews a TrustMark"""
    try:
        tm = TrustMark.objects.get(id=tmid)
        con: Redis = get_redis_connection("default")
        mark = add_trustmark(tm.domain, tm.tmt.tmtype, tm.valid_for, tm.additional_claims, con)
        # Adds the newly created JWT in the response
        tm.mark = mark
        expiry = datetime.fromtimestamp(get_expiry(mark), pytz.utc)
        tm.expire_at = expiry
        tm.save()
        return 200, tm
    except TrustMark.DoesNotExist:
        return 404, {"message": "TrustMark does not exist.", "id": tmid}
    except Exception as e:
        print(e)
        return 500, {"message": "Error while creating a new TrustMark."}


@router.put(
    "/trustmarks/{int:tmid}",
    response={200: TrustMarkOutSchema, 404: Message, 500: Message},
    tags=["TrustMarks"],
)
def update_trustmark(request: HttpRequest, tmid: int, data: TrustMarkUpdateSchema):
    """Update a TrustMark"""
    should_mark_redis_revoked = False
    try:
        tm = TrustMark.objects.get(id=tmid)
        if data.autorenew is not None:
            tm.autorenew = data.autorenew
        if data.active is not None:
            tm.active = data.active
            if not data.active:
                tm.mark = None
                should_mark_redis_revoked = True
        # Now also save any updated additional claims
        con: Redis = get_redis_connection("default")
        if data.additional_claims != tm.additional_claims:
            tm.additional_claims = data.additional_claims  # type: ignore
            # Now we should create the signed JWT and store in redis
            mark = add_trustmark(tm.domain, tm.tmt.tmtype, tm.valid_for, tm.additional_claims, con)
            tm.mark = mark
            expiry = datetime.fromtimestamp(get_expiry(mark), pytz.utc)
            tm.expire_at = expiry
        tm.save()
        if should_mark_redis_revoked:
            _ = con.hset(f"inmor:tm:{tm.domain}", tm.tmt.tmtype, "revoked")
            _ = con.srem(f"inmor:tmtype:{tm.tmt.tmtype}", tm.domain)
        return 200, tm
    except TrustMark.DoesNotExist:
        return 404, {"message": "TrustMark does not exist.", "id": tmid}
    except Exception as e:
        print(e)
        return 500, {"message": "Error while creating a new TrustMark."}


# Subordinate API


@router.post(
    "/subordinates",
    response={201: EntityOutSchema, 403: EntityOutSchema, 400: Message, 500: Message},
    tags=["Subordinates"],
)
def create_subordinate(request: HttpRequest, data: EntityTypeSchema):
    "Adds a new subordinate."
    # First get verified JWT from entity configuration with the keys we provided
    official_metadata = data.metadata
    keys = data.jwks

    # This entity_jwt is verified with the key (signature verification)
    entity_jwt, keyset, entity_jwt_str = fetch_entity_configuration(data.entityid, keys)
    claims: dict[str, Any] = json.loads(entity_jwt.claims)
    # Verify that our TA_DOMAIN is in the authority_hints of the subordinate
    authority_hints = claims.get("authority_hints", [])
    if settings.TA_DOMAIN not in authority_hints:
        return 400, {
            "message": f"TA domain {settings.TA_DOMAIN} is not in the authority_hints of the entity configuration."
        }
    # TODO: If the entity has policy, then we should try to merge to veirfy.
    if "metadata_policy" in claims:
        sub_policy = claims.get("metadata_policy", {})
        try:
            _resp = merge_our_policy_ontop_subpolicy(sub_policy)

        except Exception as e:
            print(e)
            return 400, {
                "message": f"Could not succesfully merge TA/IA POLICY on the policy of the subordinate. {e}"
            }

    metadata: dict[str, Any] = claims["metadata"]
    try:
        _ = apply_server_policy(json.dumps(metadata))

    except Exception as e:
        print(e)
        return 400, {"message": f"Could not succesfully apply POLICY on the metadata. {e}"}
    if data.valid_for:
        if data.valid_for > settings.SUBORDINATE_DEFAULT_VALID_FOR:  # Oops, we can not allow that.
            return 400, {
                "message": f"valid_for is greater than allowed by system default {settings.SUBORDINATE_DEFAULT_VALID_FOR}.",
                "id": 0,
            }
        expiry = data.valid_for
    else:
        expiry = settings.SUBORDINATE_DEFAULT_VALID_FOR

    # Now we can build the sub ordinate statement.
    now = datetime.now()
    exp = now + timedelta(hours=expiry)
    # Next, we create the signed statement
    signed_statement = create_subordinate_statement(
        data.entityid,
        keyset,
        now,
        exp,
        forced_metadata=data.forced_metadata,
        additional_claims=data.additional_claims,
    )
    # Next save the data in the database.
    if keys:
        keys_for_db = json.dumps(keys)
    else:
        keys_for_db = None
    try:
        sub_statement, created = Subordinate.objects.get_or_create(
            entityid=data.entityid,
            autorenew=data.autorenew,
            metadata=json.dumps(data.metadata),
            forced_metadata=json.dumps(data.forced_metadata),
            jwks=keys_for_db,
            valid_for=expiry,
            active=data.active,
            statement=signed_statement,
            additional_claims=data.additional_claims,
        )
    except Exception as e:
        print(e)
        if "unique constraint" in e.args[0]:
            sub_statement = Subordinate.objects.get(entityid=data.entityid)
            return 403, sub_statement
        return 500, {"message": "Error while adding a new subordinate."}
    # If we did not create a new subordinate, return now.
    if not created:
        return 403, sub_statement
    # All good so far, we will update all related redis entries now.
    con: Redis = get_redis_connection("default")
    update_redis_with_subordinate(
        data.entityid, entity_jwt_str, official_metadata, signed_statement, con
    )
    return 201, sub_statement


@router.get("/subordinates", response=list[EntityOutSchema], tags=["Subordinates"])
@paginate(LimitOffsetPagination)
def list_trust_subordinates(
    request: HttpRequest,
):
    """Lists all existing TrustMarkType(s) from database."""
    return Subordinate.objects.all()


@router.get(
    "/subordinates/{int:subid}",
    response={200: EntityOutSchema, 404: Message, 500: Message},
    tags=["Subordinates"],
)
def get_subordinate_byid(request: HttpRequest, subid: int):
    """Gets a TrustMarkType"""
    try:
        tmt = Subordinate.objects.get(id=subid)
        return tmt
    except Subordinate.DoesNotExist:
        return 404, {"message": "Subordinate could not be found.", "id": subid}
    except Exception as e:
        print(e)
        return 500, {"message": "Failed to get Subordinate.", "id": subid}


@router.post(
    "/subordinates/{int:subid}",
    response={200: EntityOutSchema, 403: EntityOutSchema, 400: Message, 500: Message},
    tags=["Subordinates"],
)
def update_subordinate(request: HttpRequest, subid: int, data: EntityTypeUpdateSchema):
    "Updates a subordinate."

    try:
        sub = Subordinate.objects.get(id=subid)
    except Subordinate.DoesNotExist:
        return 404, {"message": "Subordinate could not be found.", "id": subid}
    except Exception as e:
        print(e)
        return 500, {"message": "Failed to get Subordinate.", "id": subid}

    # First get verified JWT from entity configuration with the keys we provided
    official_metadata = data.metadata
    keys: dict[Any, Any] | None = None
    if data.jwks:
        keys = data.jwks

    # This entity_jwt is verified with the key (signature verification)
    entity_jwt, keyset, entity_jwt_str = fetch_entity_configuration(sub.entityid, keys)
    claims: dict[str, Any] = json.loads(entity_jwt.claims)
    # Verify that our TA_DOMAIN is in the authority_hints of the subordinate
    authority_hints = claims.get("authority_hints", [])
    if settings.TA_DOMAIN not in authority_hints:
        return 400, {
            "message": f"TA domain {settings.TA_DOMAIN} is not in the authority_hints of the entity configuration."
        }
    # TODO: If the entity has policy, then we should try to merge to veirfy.
    if "metadata_policy" in claims:
        sub_policy = claims.get("metadata_policy", {})
        try:
            _resp = merge_our_policy_ontop_subpolicy(sub_policy)

        except Exception as e:
            print(e)
            return 400, {
                "message": f"Could not succesfully merge TA/IA POLICY on the policy of the subordinate. {e}"
            }

    metadata: dict[str, Any] = claims["metadata"]
    try:
        _ = apply_server_policy(json.dumps(metadata))

    except Exception as e:
        print(e)
        return 400, {"message": f"Could not succesfully apply POLICY on the metadata. {e}"}
    if data.valid_for:
        if data.valid_for > settings.SUBORDINATE_DEFAULT_VALID_FOR:  # Oops, we can not allow that.
            return 400, {
                "message": f"valid_for is greater than allowed by system default {settings.SUBORDINATE_DEFAULT_VALID_FOR}.",
                "id": 0,
            }
        expiry = data.valid_for
    else:
        expiry = settings.SUBORDINATE_DEFAULT_VALID_FOR

    # Now we can build the sub ordinate statement.
    now = datetime.now()
    exp = now + timedelta(hours=expiry)
    # Next, we create the signed statement
    signed_statement = create_subordinate_statement(
        sub.entityid,
        keyset,
        now,
        exp,
        data.forced_metadata,
        additional_claims=data.additional_claims,
    )
    # Next save the data in the database.
    if keys:
        keys_for_db = json.dumps(keys)
    else:
        keys_for_db = None
    try:
        # Set each value from the input
        sub.autorenew = bool(data.autorenew)
        sub.metadata = json.dumps(data.metadata)
        sub.forced_metadata = json.dumps(data.forced_metadata)
        sub.jwks = keys_for_db
        sub.valid_for = expiry
        sub.active = bool(data.active)
        sub.additional_claims = data.additional_claims
        sub.statement = signed_statement
        sub.save()
    except Exception as e:
        print(e)
        return 500, {"message": "Error while updating the subordinate", id: subid}
    # All good so far, we will update all related redis entries now.
    con: Redis = get_redis_connection("default")
    update_redis_with_subordinate(
        sub.entityid, entity_jwt_str, official_metadata, signed_statement, con
    )
    return 200, sub


class FetchConfigSchema(Schema):
    url: Annotated[str, Field(description="The entity URL to fetch configuration from.")]


class FetchConfigOutSchema(Schema):
    metadata: Annotated[
        dict[str, Any], Field(description="Entity metadata from the configuration.")
    ]
    jwks: Annotated[dict[str, Any], Field(description="JWKS from the entity configuration.")]
    authority_hints: Annotated[
        list[str] | None, Field(description="Authority hints from the configuration.")
    ] = None
    trust_marks: Annotated[
        list[dict[str, Any]] | None, Field(description="Trust marks from the configuration.")
    ] = None


@router.post(
    "/subordinates/fetch-config",
    response={200: FetchConfigOutSchema, 400: Message, 500: Message},
    tags=["Subordinates"],
)
def fetch_entity_config(request: HttpRequest, data: FetchConfigSchema):
    """Fetches and self-validates an entity configuration from the given URL.

    This endpoint fetches the OpenID Federation entity configuration from the
    well-known endpoint, self-validates it using the embedded JWKS, and returns
    the verified claims.
    """
    try:
        payload, _jwt_str = fetch_payload(data.url)
        return 200, {
            "metadata": payload.get("metadata", {}),
            "jwks": payload.get("jwks", {}),
            "authority_hints": payload.get("authority_hints"),
            "trust_marks": payload.get("trust_marks"),
        }
    except httpx.ConnectError:
        return 400, {
            "message": f"Could not connect to {data.url}. Please check the URL and ensure the domain exists."
        }
    except httpx.TimeoutException:
        return 400, {"message": f"Connection to {data.url} timed out. Please try again."}
    except httpx.RequestError as e:
        return 400, {"message": f"Failed to reach {data.url}: {e}"}
    except Exception as e:
        error_str = str(e)
        if "Fetching payload returns" in error_str:
            # Extract status code if present
            if "404" in error_str:
                return 400, {
                    "message": f"No OpenID Federation configuration found at {data.url}/.well-known/openid-federation"
                }
            return 400, {"message": f"Failed to fetch entity configuration: {error_str}"}
        if "InvalidJWSSignature" in error_str or "signature" in error_str.lower():
            return 400, {"message": "Entity configuration signature validation failed."}
        if "Expecting value" in error_str or "Invalid" in error_str:
            return 400, {
                "message": "Invalid response from server. No valid OpenID Federation JWT found."
            }
        return 400, {"message": f"Error fetching entity configuration: {error_str}"}


@router.post("/server/entity", response={201: EntityStatement})
def create_server_entity(request: HttpRequest):
    "Creates server's entity configuration"
    token = create_server_statement()
    con: Redis = get_redis_connection("default")
    _ = con.set("inmor:entity_id", token)
    return 201, {"entity_statement": token}


@router.post("/server/historical_keys", response={201: Message, 404: Message})
def create_historical_keys(request: HttpRequest):
    """Creates signed historical keys JWT and stores in Redis.

    Reads historical key files from HISTORICAL_KEYS_DIR, filters to only
    include keys with 'exp' field, creates a signed JWT, and stores in Redis.
    """

    keys: list[dict[str, Any]] = []
    keys_dir = settings.HISTORICAL_KEYS_DIR

    # Check if directory exists
    if not os.path.isdir(keys_dir):
        return 404, {"message": f"Historical keys directory not found: {keys_dir}"}

    # Read all JSON files from the directory
    for filename in os.listdir(keys_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(keys_dir, filename)
            try:
                with open(filepath) as f:
                    key_data = json.load(f)
                    # Only include keys that have an "exp" field
                    if "exp" in key_data:
                        keys.append(key_data)
            except (json.JSONDecodeError, IOError):
                continue

    if not keys:
        return 404, {"message": "No historical keys found with exp field"}

    # Create the signed JWT
    now = datetime.now()
    claims: dict[str, Any] = {
        "iss": settings.TA_DOMAIN,
        "iat": now.timestamp(),
        "keys": keys,
    }

    token = create_signed_jwt(claims, settings.SIGNING_PRIVATE_KEY, "jwk-set+jwt")

    # Store in Redis
    con: Redis = get_redis_connection("default")
    _ = con.set("inmor:historical_keys", token)

    return 201, {"message": f"Historical keys JWT created with {len(keys)} keys"}


# Add routers to API
api.add_router("/auth", auth_router)  # Auth endpoints (no auth required)
api.add_router("", router)  # Main API (auth required)
