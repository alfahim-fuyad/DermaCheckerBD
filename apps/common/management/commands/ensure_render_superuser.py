"""Create the configured Render superuser once, without changing existing users."""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a superuser from Render environment variables if it does not exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not username and not password:
            self.stdout.write("Render superuser variables are not set; skipping.")
            return
        if not username or not password:
            raise CommandError(
                "Set both DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD."
            )
        if len(password) < 12:
            raise CommandError(
                "DJANGO_SUPERUSER_PASSWORD must be at least 12 characters long."
            )

        User = get_user_model()
        username_field = User.USERNAME_FIELD
        lookup = {username_field: username}

        try:
            existing_user = User._default_manager.get(**lookup)
        except User.DoesNotExist:
            try:
                validate_password(password)
            except ValidationError as exc:
                raise CommandError("; ".join(exc.messages)) from exc

            User._default_manager.db_manager().create_superuser(
                **{username_field: username},
                password=password,
            )
            self.stdout.write(self.style.SUCCESS("Render superuser created."))
            return

        if not existing_user.is_staff or not existing_user.is_superuser:
            raise CommandError(
                "A non-superuser already uses DJANGO_SUPERUSER_USERNAME. "
                "Choose a different username or promote that account manually."
            )

        self.stdout.write("Render superuser already exists; leaving it unchanged.")
