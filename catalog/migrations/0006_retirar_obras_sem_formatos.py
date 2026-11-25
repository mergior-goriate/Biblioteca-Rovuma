from django.db import migrations
from django.db.models import Exists, OuterRef
from django.db.models.functions import Now


def withdraw_unavailable_works(apps, schema_editor):
    Work = apps.get_model("catalog", "Work")
    Copy = apps.get_model("catalog", "Copy")
    Version = apps.get_model("documents", "Version")
    database = schema_editor.connection.alias
    copies = Copy.objects.using(database).filter(edition__work_id=OuterRef("pk"), state="local")
    versions = Version.objects.using(database).filter(
        document__edition__work_id=OuterRef("pk"), state="published",
    )
    Work.objects.using(database).filter(
        ~Exists(copies), ~Exists(versions), state="published",
    ).update(state="draft", modified=Now())


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_collection_work_collections"),
        ("documents", "0001_initial"),
    ]
    operations = [migrations.RunPython(withdraw_unavailable_works, migrations.RunPython.noop)]
