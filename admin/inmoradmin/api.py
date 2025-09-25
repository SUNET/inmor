import json
from datetime import datetime
from typing import Annotated, Any

import pytz
from django.conf import settings
from django.http import HttpRequest
from django_redis import get_redis_connection
from ninja import NinjaAPI, Router, Schema
from ninja.pagination import LimitOffsetPagination, paginate
from pydantic import Field
from redis.client import Redis

from entities.lib import apply_server_policy, fetch_entity_configuration
from trustmarks.lib import add_trustmark, get_expiry
from trustmarks.models import TrustMark, TrustMarkType

api = NinjaAPI()
router = Router()

DEFAULTS: dict[str, dict[str, Any]] = settings.TA_DEFAULTS


class TrustMarkTypeGetSchema(Schema):
    tmtype: str


class TrustMarkTypeSchema(Schema):
    tmtype: Annotated[str, Field(description="URL to describe the Trust Mark Type.")]
    autorenew: bool = DEFAULTS["trustmarktype"]["autorenew"]
    valid_for: int = DEFAULTS["trustmarktype"]["valid_for"]
    renewal_time: int = DEFAULTS["trustmarktype"]["renewal_time"]
    active: bool = DEFAULTS["trustmarktype"]["active"]


class TrustMarkTypeOutSchema(Schema):
    id: int
    tmtype: str
    autorenew: bool
    valid_for: int
    renewal_time: int
    active: bool


class TrustMarkTypeUpdateSchema(Schema):
    autorenew: bool | None = None
    valid_for: int | None = None
    renewal_time: int | None = None
    active: bool | None = None


class TrustMarkSchema(Schema):
    tmt: int
    domain: str
    autorenew: bool | None = None
    valid_for: int | None = None
    renewal_time: int | None = None
    active: bool | None = None


class TrustMarkOutSchema(Schema):
    id: int
    domain: str
    expire_at: datetime
    autorenew: bool | None = None
    valid_for: int | None = None
    renewal_time: int | None = None
    active: bool | None = None
    mark: str | None = None


class TrustMarkUpdateSchema(Schema):
    autorenew: bool | None = None
    active: bool | None = None


class TrustMarkListSchema(Schema):
    domain: str


class EntityTypeSchema(Schema):
    entityid: str
    metadata: dict[Any, Any]
    keys: str | None = None
    required_trustmarks: str | None = None
    valid_for: int | None = None
    autorenew: bool | None = None


class EntityOutSchema(Schema):
    id: int = 0
    entityid: str
    metadata: dict[Any, Any]
    keys: str | None = None
    required_trustmarks: str | None = None
    valid_for: int | None = None
    autorenew: bool | None = None


class Message(Schema):
    message: str
    id: int = 0


# API for TrustMarkTypes


@router.post(
    "/trustmarktypes",
    response={201: TrustMarkTypeOutSchema, 403: TrustMarkTypeOutSchema, 500: Message},
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


@router.get("/trustmarktypes", response=list[TrustMarkTypeOutSchema])
@paginate(LimitOffsetPagination)
def list_trust_mark_type(
    request: HttpRequest,
):
    """Lists all existing TrustMarkType(s) from database."""
    return TrustMarkType.objects.all()


@router.get(
    "/trustmarktypes/{int:tmtid}",
    response={200: TrustMarkTypeOutSchema, 404: Message, 500: Message},
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
        tm, created = TrustMark.objects.get_or_create(
            tmt=tmt,
            domain=data.domain,
            autorenew=data.autorenew,
            valid_for=data.valid_for,
            renewal_time=data.renewal_time,
            active=data.active,
        )
        con: Redis = get_redis_connection("default")
        if created:
            # Now we should create the signed JWT and store in redis

            mark = add_trustmark(tm.domain, tmt.tmtype, tm.valid_for, con)
            # Adds the newly created JWT in the response
            tm.mark = mark
            expiry = datetime.fromtimestamp(get_expiry(mark), pytz.utc)
            tm.expire_at = expiry
            tm.save()
            return 201, tm
        else:
            return 403, tm
    except Exception as e:
        print(e)
        return 500, {"message": "Error while creating a new TrustMark."}


@router.post(
    "/trustmarks/list",
    response={200: list[TrustMarkOutSchema], 403: TrustMarkOutSchema, 404: Message, 500: Message},
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
)
@paginate(LimitOffsetPagination)
def get_trustmark_list(request: HttpRequest):
    """Returns a list of existing TrustMarks."""
    return TrustMark.objects.all()


@router.post(
    "/trustmarks/{int:tmid}/renew",
    response={200: TrustMarkOutSchema, 404: Message, 500: Message},
)
def renew_trustmark(request: HttpRequest, tmid: int):
    """Renews a TrustMark"""
    try:
        tm = TrustMark.objects.get(id=tmid)
        con: Redis = get_redis_connection("default")
        mark = add_trustmark(tm.domain, tm.tmt.tmtype, tm.valid_for, con)
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
)
def update_trustmark(request: HttpRequest, tmid: int, data: TrustMarkUpdateSchema):
    """Update a TrustMark"""
    try:
        tm = TrustMark.objects.get(id=tmid)
        if data.autorenew is not None:
            tm.autorenew = data.autorenew
        if data.active is not None:
            tm.active = data.active
            if not data.active:
                tm.mark = None
        tm.save()
        # TODO: Should we remove the trustmark from redis in case it is not active?
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
)
def create_subordinate(request: HttpRequest, data: EntityTypeSchema):
    "Adds a new subordinate."
    # First get verified JWT from entity configuration with the keys we provided
    official_metadata = data.metadata
    keys: dict[Any, Any] | None = None
    if data.keys:
        keys = json.loads(data.keys)

    print(type(official_metadata))
    entity_jwt = fetch_entity_configuration(data.entityid, official_metadata, keys)
    claims: dict[str, Any] = json.loads(entity_jwt.claims)
    metadata: dict[str, Any] = claims["metadata"]
    try:
        _ = apply_server_policy(json.dumps(metadata))

    except Exception as e:
        print(e)
        return 400, {"message": f"Could not succesfully apply POLICY on the metadata. {e}"}

    return 201, data


api.add_router("", router)
