#!/usr/bin/env python3
"""Django management entry point for dermacheckerbd."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dermacheckerbd.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and on your "
            "PYTHONPATH? Did you forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
