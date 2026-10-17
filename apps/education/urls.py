from django.urls import path
from . import views

app_name = "education"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("article/<slug:slug>/", views.article_view, name="article"),
    path("<str:code>/", views.class_detail_view, name="detail"),
]
