from django import forms

from apps.predictor.models import PredictionRecord


class ReviewUpdateForm(forms.ModelForm):
    class Meta:
        model = PredictionRecord
        fields = ("review_status", "review_date")
        widgets = {
            "review_status": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "review_date": forms.DateInput(
                attrs={"class": "form-control form-control-sm", "type": "date"},
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["review_date"].input_formats = ["%Y-%m-%d"]
        self.fields["review_date"].required = False
