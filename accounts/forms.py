from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class SignupForm(forms.Form):
    name = forms.CharField(max_length=120)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    confirm = forms.CharField(widget=forms.PasswordInput)
    college = forms.CharField(max_length=120, required=False)
    course = forms.CharField(max_length=80, required=False)
    semester = forms.CharField(max_length=20, required=False)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password") and data["password"] != data.get("confirm"):
            self.add_error("confirm", "Passwords do not match.")
        elif data.get("password"):
            try:
                validate_password(data["password"])
            except forms.ValidationError as e:
                self.add_error("password", e)
        return data


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
