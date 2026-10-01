from django import forms
from django.conf import settings

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}


class GenerateForm(forms.Form):
    topic = forms.CharField(max_length=200, required=False)
    image = forms.ImageField(required=False)  # Pillow verifies it is a real image

    def clean_image(self):
        img = self.cleaned_data.get("image")
        if not img:
            return img
        if img.name.rsplit(".", 1)[-1].lower() not in ALLOWED_EXT:
            raise forms.ValidationError("Please upload a valid JPG, PNG or WEBP image.")
        if img.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError("Please upload a smaller image.")
        return img

    def clean(self):
        data = super().clean()
        if not self.errors and not (data.get("topic", "").strip() or data.get("image")):
            raise forms.ValidationError("Please enter a topic or upload an image.")
        return data
