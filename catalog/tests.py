from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from documents.models import Document, Version
from reading.models import SavedWork
from .models import Author, Collection, Copy, Edition, Identifier, Location, Work
from .views import WorkForm


class CatalogueTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = cls.create_student("0042")
        cls.editor = User.objects.create_user(username="editor", state=User.State.ACTIVE)
        cls.editor.user_permissions.add(Permission.objects.get(codename="manage_collection"))
        cls.work = Work.objects.create(
            title="Ecologia & conservação", language="Português", state=Work.State.PUBLISHED,
        )
        cls.edition = Edition.objects.create(work=cls.work, label="2.ª edição", publisher="UniRovuma", year=2025)
        cls.location = Location.objects.create(name="Sala de leitura")
        cls.copy = Copy.objects.create(edition=cls.edition, location=cls.location, inventory="R-42")

    @classmethod
    def create_student(cls, number):
        return User.objects.create_user(
            username=number, institutional_number=number, state=User.State.ACTIVE,
            credential_until=timezone.localdate() + timedelta(days=1),
        )

    def test_collection_visibility_and_combined_filter(self):
        self.client.force_login(self.editor)
        self.assertRedirects(self.client.post(reverse("new_collection"), {
            "name": "Biologia", "description": "Leituras do primeiro semestre",
        }), reverse("manage_collections"))
        collection = Collection.objects.get(name="Biologia")
        self.assertRedirects(self.client.post(reverse("edit_work", args=[self.work.pk]), {
            "title": self.work.title, "kind": self.work.kind, "language": self.work.language,
            "collections": [collection.pk],
        }), reverse("manage_work", args=[self.work.pk]))
        draft = Work.objects.create(title="Obra ainda em revisão", language="Português")
        draft.collections.add(collection)
        student = Client()
        student.force_login(self.student)
        catalogue = reverse("catalogue")
        self.assertNotContains(student.get(catalogue), collection.name)
        self.assertEqual(student.get(catalogue, {"coleccao": collection.pk}).status_code, 404)
        edit_collection = reverse("edit_collection", args=[collection.pk])
        self.assertEqual(student.post(edit_collection, {"name": "Outro nome"}).status_code, 403)
        self.assertRedirects(self.client.post(edit_collection, {
            "name": collection.name, "description": collection.description, "published": "on",
        }), reverse("manage_collections"))
        response = student.get(catalogue, {"coleccao": collection.pk, "q": "conservação", "formato": "fisico"})
        self.assertContains(response, collection.description)
        self.assertEqual(list(response.context["page"]), [self.work])
        self.assertContains(student.get(reverse("work", args=[self.work.pk])), f"?coleccao={collection.pk}")

    def test_bibliographic_export_respects_work_and_edition(self):
        self.work.authors.add(Author.objects.create(name="Ana Matola"), Author.objects.create(name="Ivo Dinis"))
        Identifier.objects.create(edition=self.edition, scheme="DOI", value="https://doi.org/10.0000/exemplo")
        Identifier.objects.create(edition=self.edition, scheme="ISBN", value="EXEMPLO")
        bib = reverse("work_bibliography", args=[self.work.pk, self.edition.pk, "bib"])
        ris = reverse("work_bibliography", args=[self.work.pk, self.edition.pk, "ris"])
        self.assertEqual(self.client.get(bib).status_code, 302)
        self.client.force_login(self.student)
        response = self.client.get(bib)
        self.assertIn(f'attachment; filename="rovuma-{self.edition.pk}.bib"', response["Content-Disposition"])
        self.assertIn("private", response["Cache-Control"])
        self.assertContains(response, r"Ecologia \& conservação")
        self.assertContains(response, "Ana Matola and Ivo Dinis")
        self.assertContains(response, "doi = {10.0000/exemplo}")
        response = self.client.get(ris)
        self.assertContains(response, "TI  - Ecologia & conservação\r\n")
        self.assertContains(response, "AU  - Ana Matola\r\n")
        self.assertContains(response, "PY  - 2025\r\n")
        self.assertContains(response, "SN  - EXEMPLO\r\n")
        self.assertTrue(response.content.endswith(b"ER  - \r\n"))
        other = Work.objects.create(title="Outra obra", language="Português", state=Work.State.PUBLISHED)
        self.assertEqual(self.client.get(reverse("work_bibliography", args=[other.pk, self.edition.pk, "bib"])).status_code, 404)
        Work.objects.filter(pk=self.work.pk).update(state=Work.State.ARCHIVED)
        self.assertEqual(self.client.get(ris).status_code, 404)

    def test_saved_works_are_private_idempotent_and_follow_publication(self):
        save = reverse("save_work", args=[self.work.pk])
        detail = reverse("work", args=[self.work.pk])
        library = reverse("library")
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(save).status_code, 405)
        for _ in range(2):
            self.assertRedirects(self.client.post(save, {"action": "save"}), detail)
        self.assertEqual(SavedWork.objects.filter(work=self.work).count(), 1)
        self.assertContains(self.client.get(library), detail)
        other = Client()
        other.force_login(self.create_student("0043"))
        self.assertNotContains(other.get(library), detail)
        self.assertRedirects(other.post(save, {"action": "remove", "source": "library"}), library)
        self.assertTrue(SavedWork.objects.filter(user=self.student, work=self.work).exists())
        Work.objects.filter(pk=self.work.pk).update(state=Work.State.ARCHIVED)
        self.assertNotContains(self.client.get(library), detail)
        self.assertEqual(self.client.post(save, {"action": "save"}).status_code, 404)
        Work.objects.filter(pk=self.work.pk).update(state=Work.State.PUBLISHED)
        self.assertRedirects(self.client.post(save, {"action": "remove", "source": "library"}), library)
        self.assertFalse(SavedWork.objects.filter(user=self.student, work=self.work).exists())

    def test_last_local_copy_unpublishes_work_without_digital_edition(self):
        self.client.force_login(self.editor)
        edit = reverse("edit_related", args=["exemplar", self.edition.pk, self.copy.pk])
        data = {"inventory": self.copy.inventory, "location": self.location.pk, "state": Copy.State.MAINTENANCE}
        document = Document.objects.create(edition=self.edition)
        version = Version.objects.create(document=document, state=Version.State.PUBLISHED, pages=1,
                                         authorization="Licença de teste", sha256="a" * 64)
        self.assertRedirects(self.client.post(edit, data), reverse("manage_work", args=[self.work.pk]))
        self.work.refresh_from_db()
        self.assertEqual(self.work.state, Work.State.PUBLISHED)
        Version.objects.filter(pk=version.pk).update(state=Version.State.ARCHIVED)
        self.assertRedirects(self.client.post(edit, data), reverse("manage_work", args=[self.work.pk]))
        self.work.refresh_from_db()
        self.assertEqual(self.work.state, Work.State.DRAFT)
        self.assertEqual(self.client.get(reverse("work", args=[self.work.pk])).status_code, 404)

    def test_metadata_save_preserves_concurrent_publication_change(self):
        self.client.force_login(self.editor)
        edit = reverse("edit_work", args=[self.work.pk])
        save_form = WorkForm.save

        def save_after_withdrawal(form, *args, **kwargs):
            Work.objects.filter(pk=self.work.pk).update(state=Work.State.DRAFT)
            return save_form(form, *args, **kwargs)

        with patch.object(WorkForm, "save", save_after_withdrawal):
            self.assertRedirects(self.client.post(edit, {
                "title": "Ecologia marinha", "kind": self.work.kind, "language": self.work.language,
            }), reverse("manage_work", args=[self.work.pk]))
        self.work.refresh_from_db()
        self.assertEqual(self.work.state, Work.State.DRAFT)
        self.assertEqual(self.work.title, "Ecologia marinha")
