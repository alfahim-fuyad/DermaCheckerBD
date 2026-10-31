"""Management command: ping the chatbot endpoint to keep the Render free-tier awake.

Render's free tier puts web services to sleep after 15 minutes of
inactivity. The first request after sleep takes 30+ seconds (cold start),
which makes the chatbot feel broken. This command pings your own health
endpoint at a configurable interval to keep the process warm.

Usage:
    # Run forever, ping every 10 minutes (default):
    python manage.py keep_chatbot_warm

    # Ping every 5 minutes against a custom URL:
    python manage.py keep_chatbot_warm --url https://your-app.onrender.com/healthz/ --interval 300

Recommended Render setup:
- Add a Render "Background Worker" with the same codebase + this command.
- Or use an external uptime monitor (UptimeRobot, cron-job.org) to ping
  /healthz/ every 10 minutes. Either approach works; the external monitor
  is simpler and doesn't consume your free-tier worker hours.
"""
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Periodically ping the app's health endpoint to prevent Render free-tier sleep."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default="",
            help=(
                "Absolute health-check URL to ping (e.g. "
                "https://your-app.onrender.com/healthz/). If omitted, "
                "the command pings itself via /healthz/ relative to the "
                "current request — only useful inside a worker that "
                "shares the web service's host."
            ),
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=600,
            help="Seconds between pings. Default 600 (10 minutes). Render sleeps after 15 min.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Ping once and exit (useful for external cron).",
        )

    def handle(self, *args, **options):
        url = (options.get("url") or "").strip()
        interval = max(60, int(options.get("interval", 600)))
        once = bool(options.get("once"))

        if not url:
            raise CommandError(
                "--url is required. Pass the absolute URL of your deployed "
                "app's /healthz/ endpoint, e.g. "
                "https://your-app.onrender.com/healthz/"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Keep-alive: pinging {url} every {interval}s"
            + (" (once)" if once else " (loop)")
        ))

        def ping():
            try:
                r = requests.get(url, timeout=10)
                ok = r.status_code == 200
                self.stdout.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"{url} -> {r.status_code} "
                    + ("OK" if ok else "WARN")
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"{url} -> error: {e}"
                ))

        if once:
            ping()
            return

        while True:
            ping()
            time.sleep(interval)
