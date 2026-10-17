#!/usr/bin/env python3
"""
Scaffold app __init__.py + apps.py + admin.py + urls.py + views.py + models.py
for the feature apps. We will overwrite specific files (models, views, templates)
later; this just gives us the baseline structure that Django needs to start.
"""
import os

APPS = ["core", "accounts", "predictor", "photo_guide", "reliability",
        "multi_image", "tracker", "chatbot", "similar_cases"]

BASE = "/home/z/my-project/apps"

for app in APPS:
    d = os.path.join(BASE, app)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "__init__.py"), "a").close()
    # apps.py
    with open(os.path.join(d, "apps.py"), "w") as f:
        f.write(
            "from django.apps import AppConfig\n\n\n"
            f"class {app.capitalize()}Config(AppConfig):\n"
            f"    default_auto_field = 'django.db.models.BigAutoField'\n"
            f"    name = 'apps.{app}'\n"
            f"    label = '{app}'\n"
        )
    # admin.py
    with open(os.path.join(d, "admin.py"), "w") as f:
        f.write("from django.contrib import admin\n\n# Register your models here.\n")
    # urls.py placeholder (will be overwritten)
    with open(os.path.join(d, "urls.py"), "w") as f:
        f.write(
            "from django.urls import path\nfrom . import views\n\n"
            f"app_name = '{app}'\n\nurlpatterns = []\n"
        )
    # views.py placeholder (will be overwritten)
    with open(os.path.join(d, "views.py"), "w") as f:
        f.write("from django.shortcuts import render\n\n# Views will be added per app.\n")

print("Scaffolded:", APPS)
