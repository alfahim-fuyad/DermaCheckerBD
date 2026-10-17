"""ASGI config for dermacheckerbd."""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dermacheckerbd.settings")
application = get_asgi_application()
