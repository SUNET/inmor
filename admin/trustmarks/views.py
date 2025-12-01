from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .forms import TrustMarkTypeForm
from .lib import TrustMarkTypeRequest
from .models import TrustMark, TrustMarkType

# Create your views here.


def index(request: HttpRequest):
    return render(request, "trustmarks/index.html")


def listtrustmarks(request: HttpRequest):
    trust_mark_list = TrustMark.objects.all()
    paginator = Paginator(trust_mark_list, 3)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "trustmarks/list.html", {"page_obj": page_obj})


def type_index(request: HttpRequest):
    return render(request, "trustmark_types/index.html")


def list_trustmark_types(request: HttpRequest):
    trust_mark_types_list = TrustMarkType.objects.all()
    paginator = Paginator(trust_mark_types_list, 3)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "trustmark_types/list.html", {"page_obj": page_obj})


def add_trustmark_type(request: HttpRequest) -> HttpResponse:
    msg = ""

    if request.method == "POST":
        form = TrustMarkTypeForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            tmr = TrustMarkTypeRequest(type=form.data["type"])
            trust_mark_type, created = TrustMarkType.objects.get_or_create(tmtype=tmr.type)
            if created:
                msg = f"Added {tmr.type}"
            else:
                msg = f"Trust mark type {tmr.type} was already present"
        else:
            print("invalid form")
            msg = "Form validation failed."
    else:
        form = TrustMarkTypeForm(request.POST)

    return render(
        request,
        "trustmark_types/add.html",
        {"form": form, "msg": msg},
    )
