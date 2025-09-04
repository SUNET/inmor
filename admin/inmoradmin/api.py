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


class Message(Schema):
    message: str
    id: int = 0


@router.post("/trustmarktypes", response={201: Message, 403: Message, 500: Message})
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
            return 201, {"message": "TrustMarkType created Succesfully.", "id": tmt.id}
        else:
            return 403, {"message": "TrustMarkType already existed.", "id": tmt.id}
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


api.add_router("", router)
