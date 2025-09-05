from typing import Any

from django.conf import settings
from django.http import HttpRequest
from ninja import NinjaAPI, Router, Schema
from ninja.pagination import LimitOffsetPagination, paginate

from trustmarks.models import TrustMarkType

api = NinjaAPI()
router = Router()

DEFAULTS: dict[str, dict[str, Any]] = settings.TA_DEFAULTS


class TrustMarkTypeSchema(Schema):
    tmtype: str
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
    autorenew: bool| None = None
    valid_for: int | None = None
    renewal_time: int | None = None
    active: bool | None = None



class Message(Schema):
    message: str
    id: int = 0


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


@router.put("/trustmarktypes/{int:tmtid}", response={200: TrustMarkTypeOutSchema, 404: Message, 500: Message})
def update_trust_mark_type(
    request: HttpRequest,
    tmtid: int,
    data: TrustMarkTypeUpdateSchema
):
    """Updates TrustMarkType"""
    try:
        updated = False
        tmt = TrustMarkType.objects.get(id=tmtid)
        if not data.active is None:
            tmt.active = data.active
            updated = True
        if not data.autorenew is None:
            tmt.autorenew = data.autorenew
            updated = True
        if not data.valid_for is None:
            tmt.valid_for = data.valid_for
            updated = True
        if not data.renewal_time is None:
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


api.add_router("", router)
