"""
URL configuration for inmoradmin project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from allauth.account.decorators import secure_admin_login
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.http import require_safe

from . import views
from .api import api

# allauth redirects anonymous users, but passes authenticated staff to this
# view. Only allow navigation there: the stock POST would accept a password.
admin.site.login = secure_admin_login(require_safe(admin.site.login))

urlpatterns = [
    path("trustmarks/", include("trustmarks.urls")),
    path("entities/", include("entities.urls")),
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
    path("accounts/", include("allauth.urls")),
    path("", views.index),
]
