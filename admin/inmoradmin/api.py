from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.pagination import LimitOffsetPagination, paginate
from trustmarks.models import TrustMarkType

api = NinjaAPI()


class TrustMarkTypeSchema(Schema):
    tmtype: str
    valid_for: int = 365  # How many days the default entry will be valid for


class Message(Schema):
    message: str
    id: int = 0


@api.post("/trust_mark_type", response={200: Message, 403: Message, 500: Message})
def create_trust_mark_type(request: HttpRequest, data: TrustMarkTypeSchema):
    """Creates a new trust_mark_type"""
    try:
        tmt, created = TrustMarkType.objects.get_or_create(
            tmtype=data.tmtype, valid_for=data.valid_for
        )
        if created:
            return {"message": "TrustMarkType created Succesfully.", "id": tmt.id}
        else:
            return 403, {"message": f"TrustMarkType already existed.", "id": tmt.id}
    except Exception as e:
        print(e)
        return 500, {"message": "Error while creating a new TrustMarkType"}


@api.get("/trust_mark_type/list", response=list[TrustMarkTypeSchema])
@paginate(LimitOffsetPagination)
def list_trust_mark_type(
    request: HttpRequest,
):
    """Lists all existing TrustMarkType(s) from database."""
    return TrustMarkType.objects.all()
