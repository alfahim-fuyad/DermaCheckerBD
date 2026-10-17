"""Common app: shared services (ML model, image quality, Gemini, PDF).

This app holds no models and no URLs. It provides reusable service modules
that other apps import.
"""
default_app_config = "apps.common.apps.CommonConfig"
