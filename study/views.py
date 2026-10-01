from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import ai_service, exports, ocr_service
from .forms import GenerateForm
from .models import ExamQuestion, StudyMaterial, VivaQuestion


def _mine(request, pk):
    return get_object_or_404(StudyMaterial, pk=pk, user=request.user)  # access control


def _fill(m, data):
    """Store validated AI output on a material, replacing any earlier generation."""
    with transaction.atomic():
        if m.source_type == "IMAGE" or not m.topic:
            m.topic = data["topic"] or m.topic or "Untitled topic"
        m.notes = data["short_notes"]
        # Persist OCR text as well: regeneration must work after the request ends.
        m.save(update_fields=["topic", "source_text", "notes", "updated_at"])
        m.exam_questions.all().delete()
        m.viva_questions.all().delete()
        ExamQuestion.objects.bulk_create([ExamQuestion(material=m, **q) for q in data["exam_questions"]])
        VivaQuestion.objects.bulk_create([VivaQuestion(material=m, **q) for q in data["viva_questions"]])


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "landing.html")


@login_required
def dashboard(request):
    form = GenerateForm()
    if request.method == "POST":
        form = GenerateForm(request.POST, request.FILES)
        if form.is_valid():
            topic, image, m = form.cleaned_data["topic"].strip(), form.cleaned_data["image"], None
            try:
                if image:
                    m = StudyMaterial.objects.create(user=request.user, source_type="IMAGE", image=image, topic=topic)
                    m.source_text = ocr_service.extract_text(m.image.path)
                else:
                    m = StudyMaterial.objects.create(user=request.user, topic=topic, source_text=topic)
                _fill(m, ai_service.generate(m.source_text))
                return redirect("result", pk=m.pk)
            except (ocr_service.OCRError, ai_service.AIError) as e:
                if m:
                    m.delete()
                messages.error(request, str(e))
        else:
            for err in form.errors.values():
                messages.error(request, err[0])
    recent = StudyMaterial.objects.filter(user=request.user, saved=True)[:5]
    return render(request, "dashboard.html", {"recent": recent})


@login_required
def result(request, pk):
    m = _mine(request, pk)
    groups = {}
    for q in m.exam_questions.all():
        groups.setdefault(q.marks, []).append(q)
    return render(request, "result.html", {"m": m, "groups": sorted(groups.items())})


@login_required
def history(request):
    return render(request, "history.html", {"items": StudyMaterial.objects.filter(user=request.user, saved=True)})


@login_required
@require_POST
def save(request, pk):
    m = _mine(request, pk)
    m.saved = not m.saved
    m.save(update_fields=["saved", "updated_at"])
    messages.success(request, "Saved to your history." if m.saved else "Removed from your history.")
    return redirect("result", pk=pk)


@login_required
@require_POST
def regenerate(request, pk):
    m = _mine(request, pk)
    try:
        _fill(m, ai_service.generate(m.source_text or m.topic, request.POST.get("mode", "fresh")))
    except ai_service.AIError as e:
        messages.error(request, str(e))
    return redirect("result", pk=pk)


@login_required
@require_POST
def delete(request, pk):
    _mine(request, pk).delete()
    messages.success(request, "Study material deleted.")
    return redirect("history")


@login_required
def download(request, pk, fmt):
    m = _mine(request, pk)
    name = slugify(m.topic) or "study-material"
    if fmt == "pdf":
        resp = HttpResponse(exports.to_pdf(m), content_type="application/pdf")
    elif fmt == "txt":
        resp = HttpResponse(exports.to_txt(m), content_type="text/plain; charset=utf-8")
    else:
        return HttpResponse("Unsupported format", status=404)
    resp["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
    return resp


def _as_dict(m):
    return {"id": m.id, "topic": m.topic, "saved": m.saved, "notes": m.notes,
            "exam_questions": list(m.exam_questions.values("marks", "question", "answer")),
            "viva_questions": list(m.viva_questions.values("question", "answer"))}


@login_required
@require_GET
def api_history(request):
    return JsonResponse({"results": [{"id": m.id, "topic": m.topic, "created_at": m.created_at}
                                     for m in StudyMaterial.objects.filter(user=request.user, saved=True)]})


@login_required
@require_http_methods(["GET", "DELETE"])
def api_detail(request, pk):
    m = _mine(request, pk)
    if request.method == "DELETE":
        m.delete()
        return JsonResponse({"deleted": True})
    return JsonResponse(_as_dict(m))
