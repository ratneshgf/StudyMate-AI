from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, SignupForm
from .models import Profile

User = get_user_model()


def signup_view(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=d["email"], email=d["email"],
                                                password=d["password"], first_name=d["name"])
                Profile.objects.create(user=user, college=d["college"], course=d["course"], semester=d["semester"])
        except IntegrityError:
            form.add_error("email", "An account with this email already exists.")
            return render(request, "registration/signup.html", {"form": form})
        login(request, user)
        return redirect("landing")
    return render(request, "registration/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("landing")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(request, username=form.cleaned_data["email"].lower(),
                            password=form.cleaned_data["password"])
        if user:
            login(request, user)
            next_url = request.GET.get("next", "")
            if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
                return redirect(next_url)
            return redirect("landing")
        messages.error(request, "Email or password is incorrect.")
    return render(request, "registration/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("landing")


@login_required
def profile_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        request.user.first_name = request.POST.get("name", request.user.first_name)[:120]
        request.user.save()
        for f in ("college", "course", "semester"):
            setattr(profile, f, request.POST.get(f, "")[:120])
        profile.save()
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(request, "profile.html", {"profile": profile})
