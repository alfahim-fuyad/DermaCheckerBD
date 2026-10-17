from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("how-it-works/", views.HowItWorksView.as_view(), name="how_it_works"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
]
