from django.conf import settings
from django.db import models


class StudyMaterial(models.Model):
    SOURCES = [("TEXT", "Text"), ("IMAGE", "Image")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="materials")
    topic = models.CharField(max_length=200)
    subject = models.CharField(max_length=120, blank=True)
    source_type = models.CharField(max_length=5, choices=SOURCES, default="TEXT")
    source_text = models.TextField(blank=True)
    image = models.ImageField(upload_to="uploads/%Y/%m/", blank=True)
    notes = models.JSONField(default=dict)  # {definition, key_points[], important_concepts[]}
    saved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.topic

    def delete(self, *args, **kwargs):
        image_name = self.image.name
        result = super().delete(*args, **kwargs)
        if image_name:
            self.image.storage.delete(image_name)
        return result


class ExamQuestion(models.Model):
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name="exam_questions")
    question = models.TextField()
    answer = models.TextField()
    marks = models.PositiveSmallIntegerField(default=2)
    difficulty = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["marks", "id"]


class VivaQuestion(models.Model):
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name="viva_questions")
    question = models.TextField()
    answer = models.TextField()
    difficulty = models.CharField(max_length=20, default="medium")

    class Meta:
        ordering = ["id"]
