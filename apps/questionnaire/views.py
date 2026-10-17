"""Views for the skin warning signs questionnaire."""
from __future__ import annotations

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .questions import QUESTIONS, evaluate


@require_http_methods(["GET", "POST"])
def questionnaire_view(request):
    """Display the questionnaire (GET) or evaluate answers (POST)."""
    result = None
    answers = {}

    if request.method == "POST":
        for q in QUESTIONS:
            value = (request.POST.get(q["id"], "") or "").strip().lower()
            if value in ("yes", "no", "unsure"):
                answers[q["id"]] = value
        result = evaluate(answers, language=getattr(request, "LANGUAGE_CODE", "en"))

    return render(request, "questionnaire/questionnaire.html", {
        "questions": QUESTIONS,
        "answers": answers,
        "result": result,
    })
