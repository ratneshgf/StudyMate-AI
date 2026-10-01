from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Optional student details (FR-01)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    college = models.CharField(max_length=120, blank=True)
    course = models.CharField(max_length=80, blank=True)
    semester = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username
