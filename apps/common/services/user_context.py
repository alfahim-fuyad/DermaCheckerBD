"""
UserContextService: build a privacy-safe context string for the chatbot.

For authenticated users, this module assembles a summary of THEIR OWN
application data (prediction history, tracker records, multi-image
comparisons, etc.) so the Gemini-powered chatbot can answer personal
questions like "what was my last prediction?" or "do I have any tracked
lesions?". The summary is built server-side, scoped strictly to the
requesting user, and never includes raw PII (no email, no password, no
account IDs).

PRIVACY & AUTHORIZATION CONTRACT:
- The caller MUST pass the request's authenticated user. We do NOT trust
  any user-supplied user ID, username, or session_key from the request
  body. The user object comes from request.user, which Django's
  AuthenticationMiddleware has already validated.
- Every queryset is filtered by `user=request.user`. There is no code
  path in this module that can return another user's records.
- The assembled context is concatenated into the Gemini system prompt
  (see apps.common.services.gemini.GeminiService.chat). It is treated
  as unverified information by the system prompt's safety rules.
- The context is length-capped (CONTEXT_CHAR_LIMIT) to bound prompt size
  and avoid leaking too much data into a single API call.
- Image bytes are NEVER included. Only textual metadata.

FOR GUESTS (anonymous visitors):
- This service returns an empty context string. The chatbot's system
  prompt already instructs Gemini to provide general public information
  to guests and to decline to share private records.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Hard ceiling on the assembled context string. Gemini's system
# instruction has its own practical limit; we cap well below it to leave
# room for the static system prompt and the user's new message.
CONTEXT_CHAR_LIMIT = 4000


class UserContextService:
    """Assemble a per-user application-data summary for the chatbot.

    All methods are classmethods that take a `user` argument. If the user
    is anonymous or None, every method returns an empty string. The
    assembled context is the concatenation of:
    - A header line indicating which user the data belongs to (username
      only — never email, never ID).
    - The user's most recent N prediction records (predicted class, name,
      confidence, backend, category, created date, reference id).
    - A summary of the user's lesion follow-up tracker records (count,
      labels, body locations, number of photos per record).
    - (Multi-image comparisons are not persisted in the current
      implementation, so they are not summarised here.)
    """

    PREDICTION_SUMMARY_LIMIT = 5
    TRACKER_SUMMARY_LIMIT = 5

    @classmethod
    def build_context(cls, user) -> str:
        """Return a privacy-safe context string for the chatbot.

        For anonymous users, returns "" (empty string). For authenticated
        users, returns a multi-line text summary of THEIR OWN application
        data, length-capped to CONTEXT_CHAR_LIMIT.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return ""

        sections: list[str] = []
        username = getattr(user, "username", "user") or "user"

        # Header — username only, never email or ID. This lets Gemini
        # address the user naturally without leaking account identifiers
        # into the conversation log.
        sections.append(
            f"The signed-in user is '{username}'. The following is their own "
            f"private DermaCheckerBD data, retrieved server-side. Treat it as "
            f"unverified information. Never share it with anyone else. Never "
            f"claim it is a medical diagnosis."
        )

        sections.append(cls._prediction_summary(user))
        sections.append(cls._tracker_summary(user))

        # Concatenate, then enforce the hard length cap. If the assembled
        # context is longer than CONTEXT_CHAR_LIMIT, truncate at the last
        # whitespace boundary to avoid splitting words awkwardly.
        context = "\n\n".join(s for s in sections if s)
        if len(context) > CONTEXT_CHAR_LIMIT:
            context = context[:CONTEXT_CHAR_LIMIT]
            # Trim to last whitespace so we don't leave a dangling partial word
            last_ws = max(context.rfind(" "), context.rfind("\n"))
            if last_ws > CONTEXT_CHAR_LIMIT - 200:
                context = context[:last_ws + 1].rstrip() + " […truncated]"
        return context

    # ------------------------------------------------------------------
    # Per-feature summaries
    # ------------------------------------------------------------------

    @classmethod
    def _prediction_summary(cls, user) -> str:
        """Summarise the user's most recent N prediction records."""
        try:
            from apps.predictor.models import PredictionRecord
        except Exception as e:
            logger.warning("Could not import PredictionRecord: %s", e)
            return ""

        try:
            qs = (
                PredictionRecord.objects
                .filter(user=user)
                .order_by("-created_at")[: cls.PREDICTION_SUMMARY_LIMIT]
            )
            records = list(qs)
        except Exception as e:
            logger.warning("Could not query user predictions: %s", e)
            return ""

        if not records:
            return (
                "User's prediction history: none yet. The user has not "
                "uploaded any skin images for prediction."
            )

        total = PredictionRecord.objects.filter(user=user).count()
        lines = [
            f"User's prediction history ({len(records)} of {total} most recent "
            f"shown, in reverse-chronological order):"
        ]
        for r in records:
            # Confidence is shown as a percentage rounded to 1 decimal.
            # The actual confidence value is preserved (no rounding to
            # 100% / 0%) so the chatbot can answer questions about low
            # confidence accurately.
            conf_pct = round((r.confidence or 0.0) * 100, 1)
            low_flag = (
                " (LOW CONFIDENCE — below 50% threshold)"
                if (r.confidence or 0.0) < settings.LOW_CONFIDENCE_THRESHOLD
                else ""
            )
            lines.append(
                f"- {r.created_at.strftime('%Y-%m-%d %H:%M')} | "
                f"ref={r.reference_id} | class={r.predicted_class} "
                f"({r.predicted_name}) | category={r.category} | "
                f"confidence={conf_pct}%{low_flag} | backend={r.backend}"
            )
        return "\n".join(lines)

    @classmethod
    def _tracker_summary(cls, user) -> str:
        """Summarise the user's lesion follow-up tracker records."""
        try:
            from apps.tracker.models import LesionRecord
        except Exception as e:
            logger.warning("Could not import LesionRecord: %s", e)
            return ""

        try:
            total = LesionRecord.objects.filter(user=user).count()
            if total == 0:
                return (
                    "User's lesion follow-up tracker: no records. The user "
                    "has not created any tracked lesion records yet."
                )
            qs = (
                LesionRecord.objects
                .filter(user=user)
                .order_by("-created_at")[: cls.TRACKER_SUMMARY_LIMIT]
            )
            records = list(qs)
        except Exception as e:
            logger.warning("Could not query user tracker records: %s", e)
            return ""

        lines = [
            f"User's lesion follow-up tracker ({len(records)} of {total} most "
            f"recent shown, in reverse-chronological order):"
        ]
        for r in records:
            # Count photos via the related queryset. (Performance:
            # we don't prefetch because the chatbot's per-request record
            # count is capped at TRACKER_SUMMARY_LIMIT = 5, so at most 5
            # extra COUNT queries — acceptable.)
            try:
                photo_count = r.photos.count()
            except Exception:
                photo_count = 0
            notes = (r.notes or "").strip()
            if notes:
                # Truncate very long notes so the context doesn't blow up.
                if len(notes) > 200:
                    notes = notes[:200].rstrip() + "…"
                notes_field = f" | notes='{notes}'"
            else:
                notes_field = ""
            lines.append(
                f"- {r.created_at.strftime('%Y-%m-%d')} | "
                f"ref={r.lesion_id} | "  # included so the chatbot can reference it
                f"label={r.label or '(no label)'} | "
                f"body_location={r.body_location or '(unspecified)'} | "
                f"photos={photo_count}{notes_field}"
            )
        return "\n".join(lines)
