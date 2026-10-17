from django.urls import path
from . import views

app_name = "similar_cases"

urlpatterns = [
    path("", views.explorer_view, name="explorer"),
]
