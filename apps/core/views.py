"""Static pages: home, about, how_it_works, privacy."""
from django.shortcuts import render
from django.views.generic import TemplateView
from apps.common.services.prediction import PredictionService


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["classes"] = PredictionService.class_metadata()
        return ctx


class AboutView(TemplateView):
    template_name = "core/about.html"


class HowItWorksView(TemplateView):
    template_name = "core/how_it_works.html"


class PrivacyView(TemplateView):
    template_name = "core/privacy.html"
