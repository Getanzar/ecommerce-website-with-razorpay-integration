from django.urls import include, path
from django.http import HttpResponse


urlpatterns = [
    path("", lambda request: HttpResponse("home"), name="home"),
    path("accounts/", include("accounts.urls")),
]
