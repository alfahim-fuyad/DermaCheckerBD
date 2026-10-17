from django.urls import path
from . import views

app_name = "questionnaire"

urlpatterns = [
    path("", views.questionnaire_view, name="form"),
]
