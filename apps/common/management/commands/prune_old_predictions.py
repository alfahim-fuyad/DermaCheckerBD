"""Management command: prune old prediction & tracker records.

Honours the IMAGE_RETENTION_DAYS setting (0 = keep forever). Also deletes
the linked image files via the storage API so disk/S3 usage stays bounded.

Designed to be invoked by a Render cron job:

    python manage.py prune_old_predictions

Recommended schedule: daily at off-peak hours (e.g. 04:00 UTC).
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.predictor.models import PredictionRecord
from apps.tracker.models import FollowUpPhoto, LesionRecord

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Delete prediction and tracker records older than IMAGE_RETENTION_DAYS. "
        "A retention value of 0 means 'keep forever' (no-op)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without actually deleting.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override IMAGE_RETENTION_DAYS for this run.",
        )

    def handle(self, *args, **options):
        days = options["days"] if options["days"] is not None else getattr(
            settings, "IMAGE_RETENTION_DAYS", 0
        )
        if not days or days <= 0:
            self.stdout.write(
                "IMAGE_RETENTION_DAYS is 0 / unset — retention disabled, nothing to prune."
            )
            return

        cutoff = timezone.now() - timedelta(days=days)
        dry = options["dry_run"]

        self.stdout.write(
            f"Pruning records older than {cutoff.isoformat()} "
            f"({days} day(s); dry_run={dry})"
        )

        # Predictions
        old_preds = PredictionRecord.objects.filter(created_at__lt=cutoff)
        pred_count = old_preds.count()
        self.stdout.write(f"  PredictionRecords candidate: {pred_count}")
        if not dry and pred_count:
            for r in old_preds.iterator():
                if r.image:
                    try:
                        r.image.delete(save=False)
                    except Exception as e:
                        logger.warning("Failed to delete image %s: %s", r.reference_id, e)
            old_preds.delete()

        # Tracker photos (by photo created_at, not lesion created_at — a
        # lesion may span months of legitimate follow-up)
        old_photos = FollowUpPhoto.objects.filter(created_at__lt=cutoff)
        photo_count = old_photos.count()
        self.stdout.write(f"  FollowUpPhotos candidate: {photo_count}")
        if not dry and photo_count:
            for p in old_photos.iterator():
                if p.image:
                    try:
                        p.image.delete(save=False)
                    except Exception as e:
                        logger.warning("Failed to delete tracker photo %s: %s", p.id, e)
            old_photos.delete()

        # Tracker records with no remaining photos AND older than cutoff
        old_lesions = LesionRecord.objects.filter(
            created_at__lt=cutoff, photos__isnull=True
        )
        lesion_count = old_lesions.count()
        self.stdout.write(f"  empty LesionRecords candidate: {lesion_count}")
        if not dry and lesion_count:
            old_lesions.delete()

        self.stdout.write(self.style.SUCCESS("Prune complete."))
