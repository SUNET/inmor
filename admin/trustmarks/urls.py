from django.urls import path

from . import views

app_name = "trustmarks"

urlpatterns = [
    path("", views.index, name="index"),
]
