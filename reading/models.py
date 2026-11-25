from django.conf import settings
from django.db import models

from documents.models import Version


class Progress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version = models.ForeignKey(Version, on_delete=models.PROTECT)
    page = models.PositiveIntegerField()
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "version"), name="one_progress_per_version")]


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version = models.ForeignKey(Version, on_delete=models.PROTECT)
    page = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "version", "page"), name="unique_bookmark_page")]


class SavedWork(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey("catalog.Work", related_name="saved_entries", on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "work"), name="one_saved_entry_per_work")]
