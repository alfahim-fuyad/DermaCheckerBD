from django.urls import path
from . import views

app_name = "multi_image"

urlpatterns = [
    path("", views.compare_view, name="compare"),
]
