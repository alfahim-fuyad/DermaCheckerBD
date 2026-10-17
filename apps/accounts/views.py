"""User account views: signup, login (use Django's built-in), profile, dashboard."""
from collections import Counter
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.common.services.prediction import PredictionService
from apps.accounts.models import PatientProfile
from apps.predictor.models import PredictionRecord
from apps.tracker.models import LesionRecord


class SignupForm(UserCreationForm):
    """Built-in Django user creation form, no custom fields."""

    class Meta(UserCreationForm.Meta):
        fields = ("username",)


class ProfileForm(forms.ModelForm):
    """Edit the account's display name and email address."""

    name = forms.CharField(
        max_length=150,
        required=False,
        label="Name",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
    )

    class Meta:
        model = get_user_model()
        fields = ("email",)
        widgets = {
            "email": forms.EmailInput(
                attrs={"class": "form-control", "autocomplete": "email"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.initial.setdefault(
                "name",
                " ".join(part for part in (
                    self.instance.first_name, self.instance.last_name
                ) if part),
            )

    def save(self, commit=True):
        user = super().save(commit=False)
        name_parts = self.cleaned_data["name"].strip().split(maxsplit=1)
        user.first_name = name_parts[0] if name_parts else ""
        user.last_name = name_parts[1] if len(name_parts) > 1 else ""
        if commit:
            user.save()
        return user


class PatientProfileForm(forms.ModelForm):
    """Patient contact and demographic details."""

    class Meta:
        model = PatientProfile
        fields = ("phone", "sex", "age", "location")
        widgets = {
            "phone": forms.TextInput(attrs={
                "class": "form-control", "autocomplete": "tel", "type": "tel",
            }),
            "sex": forms.Select(attrs={"class": "form-select"}),
            "age": forms.NumberInput(attrs={
                "class": "form-control", "min": 0, "max": 130,
            }),
            "location": forms.TextInput(attrs={
                "class": "form-control", "autocomplete": "address-level2",
            }),
        }


@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("core:home")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    user = request.user
    patient_profile, _ = PatientProfile.objects.get_or_create(user=user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=user)
        details_form = PatientProfileForm(request.POST, instance=patient_profile)
        if form.is_valid() and details_form.is_valid():
            form.save()
            details_form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("account_profile")
    else:
        form = ProfileForm(instance=user)
        details_form = PatientProfileForm(instance=patient_profile)
    ctx = {
        "user": user,
        "form": form,
        "patient_profile": patient_profile,
        "details_form": details_form,
        "predictions_count": PredictionRecord.objects.filter(user=user).count(),
        "tracked_lesions": LesionRecord.objects.filter(user=user).count(),
        "recent_predictions": PredictionRecord.objects.filter(user=user).order_by("-created_at")[:5],
    }
    return render(request, "registration/profile.html", ctx)


@login_required
def dashboard_view(request):
    """Real-data dashboard for an authenticated user.

    Aggregates:
      - Total predictions
      - Saved images (alias of total predictions; one image per record)
      - Tracked lesions
      - Reports available (also total predictions; each has a PDF)
      - 7-day activity sparkline
      - Per-class prediction distribution (for the chart)
      - Top category (benign / malignant / pre malignant)
      - Recent activity feed (predictions + tracker updates merged)
    """
    user = request.user
    predictions_qs = PredictionRecord.objects.filter(user=user)
    tracker_qs = LesionRecord.objects.filter(user=user)

    total_predictions = predictions_qs.count()
    total_tracker = tracker_qs.count()
    reports_available = total_predictions  # each prediction has a PDF

    # 7-day activity
    today = timezone.now().date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily_counts = []
    for d in days:
        next_day = d + timedelta(days=1)
        c = predictions_qs.filter(
            created_at__date__gte=d, created_at__date__lt=next_day
        ).count()
        daily_counts.append({"date": d.isoformat(), "count": c})

    # Per-class distribution
    class_dist_qs = (
        predictions_qs
        .values("predicted_class")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    counts_by_class = {row["predicted_class"]: row["n"] for row in class_dist_qs}
    class_distribution = [
        {
            "code": meta["code"],
            "name": meta["name"],
            "category": meta["category"],
            "count": counts_by_class.get(meta["code"], 0),
        }
        for meta in PredictionService.class_metadata()
    ]

    # Category totals
    category_counts = Counter(
        {item["category"]: 0 for item in PredictionService.class_metadata()}
    )
    for r in predictions_qs:
        category_counts[r.category] += 1
    # normalise keys for display
    category_distribution = [
        {"category": cat, "count": n}
        for cat, n in sorted(category_counts.items())
    ]

    # Recent activity (last 5 of each, merged)
    recent_preds = list(
        predictions_qs.order_by("-created_at")[:5].values(
            "reference_id", "predicted_class", "predicted_name",
            "image_name", "created_at"
        )
    )
    recent_lesions = list(
        tracker_qs.order_by("-updated_at")[:5].values(
            "lesion_id", "label", "updated_at"
        )
    )
    activity_feed = []
    for p in recent_preds:
        activity_feed.append({
            "type": "prediction",
            "code": p["predicted_class"],
            "label": p["predicted_name"],
            "image_name": p["image_name"] or p["predicted_name"],
            "when": p["created_at"],
            "url_name": "predictor:result",
            "url_arg": p["reference_id"],
            "icon": "scan-search",
        })
    for t in recent_lesions:
        activity_feed.append({
            "type": "tracker",
            "label": t["label"],
            "when": t["updated_at"],
            "url_name": "tracker:detail",
            "url_arg": t["lesion_id"],
            "icon": "calendar-clock",
        })
    activity_feed.sort(key=lambda x: x["when"], reverse=True)
    activity_feed = activity_feed[:8]

    # Quick-action shortcuts
    quick_actions = [
        {"label": "New Prediction", "icon": "scan-search",
         "url_name": "predictor:upload", "kind": "primary"},
        {"label": "Find a Doctor", "icon": "map-pin",
         "url_name": "doctors:finder", "kind": "outline"},
        {"label": "Compare Images", "icon": "layers",
         "url_name": "multi_image:compare", "kind": "outline"},
        {"label": "View History", "icon": "history",
         "url_name": "predictor:history", "kind": "outline"},
        {"label": "Reliability Check", "icon": "activity",
         "url_name": "reliability:check", "kind": "outline"},
        {"label": "Tracker", "icon": "calendar-clock",
         "url_name": "tracker:index", "kind": "outline"},
        {"label": "Skin Health Library", "icon": "book-open",
         "url_name": "education:index", "kind": "outline"},
        {"label": "Warning Signs", "icon": "alert-triangle",
         "url_name": "questionnaire:form", "kind": "outline"},
    ]

    ctx = {
        "user": user,
        "stats": {
            "total_predictions": total_predictions,
            "saved_images": total_predictions,
            "tracked_lesions": total_tracker,
            "reports_available": reports_available,
        },
        "daily_counts": daily_counts,
        "class_distribution": class_distribution,
        "category_distribution": category_distribution,
        "activity_feed": activity_feed,
        "quick_actions": quick_actions,
    }
    return render(request, "registration/dashboard.html", ctx)
