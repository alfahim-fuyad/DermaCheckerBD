from django.urls import path
from . import views

app_name = "reliability"

urlpatterns = [
    path("", views.check_view, name="check"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
]
