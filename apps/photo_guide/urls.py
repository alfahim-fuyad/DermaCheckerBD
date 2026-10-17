from django.urls import path
from . import views

app_name = "photo_guide"

urlpatterns = [
    path("", views.quality_check_view, name="quality_check"),
]
