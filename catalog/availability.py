from audit.models import record
from documents.models import Version

from .models import Copy, Work


def has_consultable_format(work):
    return (
        Copy.objects.filter(edition__work=work, state=Copy.State.LOCAL).exists()
        or Version.objects.filter(document__edition__work=work, state=Version.State.PUBLISHED).exists()
    )


def unpublish_if_unavailable(work, user):
    # Callers hold the work's row lock while changing its availability.
    if work.state == Work.State.PUBLISHED and not has_consultable_format(work):
        work.state = Work.State.DRAFT
        work.save(update_fields=["state", "modified"])
        record(user, "collection", "Retirou obra sem formato consultável", work.pk, state=work.state)
        return True
    return False
