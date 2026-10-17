"""Views for the education app: index + per-class detail page + library articles."""
from __future__ import annotations

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .content import (
    EDUCATION_CONTENT, LIBRARY_ARTICLES, all_articles, all_classes,
    get_article, get_class_info,
)


@require_http_methods(["GET"])
def index_view(request):
    """Landing page: list of all HAM10000 classes + library articles."""
    return render(request, "education/index.html", {
        "classes": all_classes(),
        "articles": all_articles(),
    })


@require_http_methods(["GET"])
def class_detail_view(request, code: str):
    """Per-class detail page with overview, appearance, symptoms, care, references."""
    code = (code or "").lower().strip()
    info = get_class_info(code)
    if info is None:
        raise Http404("Unknown skin lesion class.")
    return render(request, "education/detail.html", {
        "info": info,
        "all_classes": all_classes(),
    })


@require_http_methods(["GET"])
def article_view(request, slug: str):
    """General skin health library article (ABCDE, sun protection, etc.)."""
    slug = (slug or "").strip().lower()
    article = get_article(slug)
    if article is None:
        raise Http404("Unknown article.")
    return render(request, "education/article.html", {
        "article": article,
        "all_articles": all_articles(),
    })
