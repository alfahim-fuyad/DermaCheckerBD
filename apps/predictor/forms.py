"""Forms for the predictor app."""
from django import forms


class ImageUploadForm(forms.Form):
    """Single-image upload form. The actual validation is done in the view
    (file-type, file-size, integrity) because Django forms don't natively
    cover all our checks."""
    image_name = forms.CharField(
        label="Image name",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "autocomplete": "off",
            "placeholder": "Enter an image name",
        }),
    )
    image = forms.FileField(
        label="Skin lesion image",
        help_text="JPG, PNG, or WEBP. Max 10 MB.",
        widget=forms.ClearableFileInput(attrs={
            "accept": "image/jpeg,image/png,image/webp",
            "class": "form-control",
            "id": "id_image_file",
        }),
    )


class MultiImageUploadForm(forms.Form):
    """Multi-image upload form (for the Multi-Image Disagreement feature).

    NOTE: Django's ClearableFileInput doesn't support the HTML 'multiple'
    attribute natively. The multi_image app uses a plain ClearableFileInput
    in its view (request.FILES.getlist('images')) rather than this form.
    This class is kept for documentation purposes only.
    """
    images = forms.FileField(
        label="Multiple photos of the same lesion",
        widget=forms.ClearableFileInput(attrs={
            "accept": "image/jpeg,image/png,image/webp",
            "class": "form-control",
        }),
    )
