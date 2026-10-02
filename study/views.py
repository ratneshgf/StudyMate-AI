import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import close_old_connections, transaction
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import ai_service, exports, ocr_service
from .forms import GenerateForm
from .models import ExamQuestion, StudyMaterial, VivaQuestion
from .quiz import build_quiz


def _mine(request, pk):
    return get_object_or_404(StudyMaterial, pk=pk, user=request.user)  # access control


def _fill(m, data):
    """Store validated AI output on a material, replacing any earlier generation."""
    with transaction.atomic():
        if m.source_type == "IMAGE" or not m.topic:
            m.topic = data["topic"] or m.topic or "Untitled topic"
        m.notes = {**data["short_notes"], "related_topics": data["related_topics"],
                   "topic_kind": data["topic_kind"], "mcq_questions": data["mcq_questions"],
                   "generation_version": 2}
        # Persist OCR text as well: regeneration must work after the request ends.
        m.save(update_fields=["topic", "source_text", "notes", "updated_at"])
        m.exam_questions.all().delete()
        m.viva_questions.all().delete()
        ExamQuestion.objects.bulk_create([ExamQuestion(material=m, **q) for q in data["exam_questions"]])
        VivaQuestion.objects.bulk_create([VivaQuestion(material=m, **q) for q in data["viva_questions"]])


def landing(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return render(request, "landing.html")


def _cached_material(user, topic):
    """Reuse only this user's complete, current-format material on repeat searches."""
    material = (StudyMaterial.objects.filter(
        user=user, source_type="TEXT", source_text__iexact=topic,
        notes__generation_version=2).prefetch_related("exam_questions", "viva_questions").first())
    if material is None:
        return None
    try:
        ai_service._parse(json.dumps({
            "topic": material.topic,
            "short_notes": material.notes,
            "related_topics": material.notes.get("related_topics"),
            "mcq_questions": material.notes.get("mcq_questions"),
            "exam_questions": [{"question": q.question, "answer": q.answer,
                                "difficulty": q.difficulty, "marks": q.marks}
                               for q in material.exam_questions.all()],
            "viva_questions": [{"question": q.question, "answer": q.answer,
                                "difficulty": q.difficulty}
                               for q in material.viva_questions.all()],
        }), quantitative=ai_service.is_quantitative(topic))
    except ai_service.AIError:
        return None
    return material


def _stream_generation(request, topic, image):
    def line(event):
        return json.dumps(event) + "\n"

    def events():
        material = None
        completed = False
        try:
            yield line({"stage": "starting"})
            if not image:
                cached = _cached_material(request.user, topic)
                if cached is not None:
                    yield line({"stage": "redirect", "url": reverse("result", args=[cached.pk])})
                    return
            material = StudyMaterial.objects.create(
                user=request.user, topic=topic, source_text=topic,
                source_type="IMAGE" if image else "TEXT", **({"image": image} if image else {}))
            if image:
                yield line({"stage": "reading"})
                material.source_text = ocr_service.extract_text(material.image.path)
            for event in ai_service.iter_generate(material.source_text):
                if event["stage"] == "complete":
                    _fill(material, event["data"])
                    completed = True
                    yield line({"stage": "redirect", "url": reverse("result", args=[material.pk])})
                else:
                    yield line(event)
        except (ocr_service.OCRError, ai_service.AIError) as exc:
            yield line({"stage": "error", "message": str(exc)})
        finally:
            if material is not None and not completed:
                material.delete()
            close_old_connections()

    response = StreamingHttpResponse(events(), content_type="application/x-ndjson")
    response["Cache-Control"] = "no-cache, no-store"
    response["X-Accel-Buffering"] = "no"
    return response


@login_required
def dashboard(request):
    form = GenerateForm()
    if request.method == "POST":
        form = GenerateForm(request.POST, request.FILES)
        if form.is_valid():
            topic, image, m = form.cleaned_data["topic"].strip(), form.cleaned_data["image"], None
            if "application/x-ndjson" in request.headers.get("Accept", ""):
                return _stream_generation(request, topic, image)
            try:
                if not image:
                    cached = _cached_material(request.user, topic)
                    if cached is not None:
                        messages.info(request, "Opened your existing study material. Use New set for fresh questions.")
                        return redirect("result", pk=cached.pk)
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
            if "application/x-ndjson" in request.headers.get("Accept", ""):
                return JsonResponse({"error": " ".join(str(err[0]) for err in form.errors.values())}, status=400)
            for err in form.errors.values():
                messages.error(request, err[0])
    recent = StudyMaterial.objects.filter(user=request.user, saved=True)[:5]
    return render(request, "dashboard.html", {"recent": recent})


@login_required
def result(request, pk):
    m = _mine(request, pk)
    levels = ("easy", "medium", "advanced")
    exam_questions = list(m.exam_questions.all())
    viva_questions = list(m.viva_questions.all())
    exam_levels = [(level, [q for q in exam_questions if (q.difficulty or "medium") == level])
                   for level in levels]
    viva_levels = [(level, [q for q in viva_questions if (q.difficulty or "medium") == level])
                   for level in levels]
    quiz = build_quiz(m)
    quiz_levels = [(level, [q for q in quiz if q["difficulty"] == level]) for level in levels]
    if any(q["difficulty"] == "practice" for q in quiz):
        quiz_levels = [("practice", quiz)]
    return render(request, "result.html", {"m": m, "exam_levels": exam_levels,
                  "viva_levels": viva_levels, "quiz": quiz, "quiz_levels": quiz_levels})


@login_required
@require_POST
def new_quiz(request, pk):
    material = _mine(request, pk)
    try:
        payload = json.loads(request.body)
        version = int(payload.get("version", 1))
        previous = payload.get("previous_questions", [])
        if not isinstance(previous, list) or len(previous) > 10:
            raise ValueError
        previous = [q[:2000] for q in previous if isinstance(q, str)]
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid test request."}, status=400)
    if version < 1 or version > 100000:
        return JsonResponse({"error": "Invalid test request."}, status=400)
    bank = material.notes.get("mcq_questions")
    if isinstance(bank, list) and len(bank) >= 10:
        existing = {q.question for q in material.exam_questions.all()}
        existing.update(q.question for q in material.viva_questions.all())
        existing.update(q.get("question", "") for q in bank if isinstance(q, dict))
        existing.update(previous)
        try:
            fresh = ai_service.generate_new_mcqs(material.source_text or material.topic, existing)
        except ai_service.AIError as exc:
            return JsonResponse({"error": str(exc)}, status=503)
        questions = build_quiz(material, version=version, bank_override=fresh)
    else:
        questions = build_quiz(material, version=version)
    if not questions:
        return JsonResponse({"error": "Generate a new set with 10 related topics first."}, status=409)
    return JsonResponse({"questions": questions})


@login_required
def history(request):
    return render(request, "history.html", {"items": StudyMaterial.objects.filter(user=request.user)})


@login_required
@require_POST
def save(request, pk):
    m = _mine(request, pk)
    m.saved = not m.saved
    m.save(update_fields=["saved", "updated_at"])
    messages.success(request, "Added to saved topics." if m.saved else "Removed from saved topics. This topic remains in your history.")
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
            "exam_questions": list(m.exam_questions.values("marks", "difficulty", "question", "answer")),
            "viva_questions": list(m.viva_questions.values("difficulty", "question", "answer"))}


@login_required
@require_GET
def api_history(request):
    return JsonResponse({"results": [{"id": m.id, "topic": m.topic, "created_at": m.created_at}
                                     for m in StudyMaterial.objects.filter(user=request.user)]})


@login_required
@require_http_methods(["GET", "DELETE"])
def api_detail(request, pk):
    m = _mine(request, pk)
    if request.method == "DELETE":
        m.delete()
        return JsonResponse({"deleted": True})
    return JsonResponse(_as_dict(m))
