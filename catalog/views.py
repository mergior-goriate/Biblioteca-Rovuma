from io import BytesIO
import logging
import os
from tempfile import mkstemp

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.db import IntegrityError, transaction
from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Exists, OuterRef, Prefetch
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from accounts.access import EDITOR, can_manage, has, permission, require, student
from audit.models import record
from documents.models import Version
from reading.models import Bookmark, Progress, SavedWork
from .availability import has_consultable_format, unpublish_if_unavailable
from .bibliography import as_bibtex, as_ris
from .models import Author, Collection, Copy, Edition, Identifier, Location, Subject, Work
from .sample_assets import KEYS, PREFIX, SCHEME, asset


logger = logging.getLogger(__name__)


def allowed(user):
    return student(user) or has(user, EDITOR)


def visible():
    return Work.objects.filter(state=Work.State.PUBLISHED).prefetch_related(
        Prefetch("authors", queryset=Author.objects.order_by("pk")), "subjects", "editions__identifiers",
    )


def with_formats(works):
    return works.annotate(
        digital=Exists(Version.objects.filter(document__edition__work=OuterRef("pk"), state=Version.State.PUBLISHED)),
        physical=Exists(Copy.objects.filter(edition__work=OuterRef("pk"), state=Copy.State.LOCAL)),
    )


def available_readings(model, user):
    return model.objects.filter(user=user, version__state=Version.State.PUBLISHED,
        version__document__edition__work__state=Work.State.PUBLISHED
    ).select_related("version__document__edition__work")


@require(lambda user: user.is_authenticated)
def home(request):
    if not student(request.user) and can_manage(request.user):
        return redirect("management")
    return redirect("portal")


@require(lambda user: user.is_authenticated)
def portal(request):
    if not allowed(request.user):
        return render(request, "staff_home.html")
    recent = available_readings(Progress, request.user).order_by("-updated")[:6] if student(request.user) else []
    featured = with_formats(visible()).order_by("is_demo", "-modified", "-pk")[:4]
    return render(request, "home.html", {"recent": recent, "featured": featured})


@require(allowed)
def catalogue(request):
    qs = visible()
    q = request.GET.get("q", "").strip()[:200]
    kind = request.GET.get("tipo", "")
    language = request.GET.get("idioma", "")
    year = request.GET.get("ano", "")
    fmt = request.GET.get("formato", "")
    collections = Collection.objects.filter(published=True)
    collection_id = request.GET.get("coleccao", "")
    selected_collection = None
    if collection_id:
        if not (collection_id.isascii() and collection_id.isdigit() and len(collection_id) <= 19):
            raise Http404
        selected_id = int(collection_id)
        if selected_id > 2**63 - 1:
            raise Http404
        selected_collection = get_object_or_404(collections, pk=selected_id)
        qs = qs.filter(collections=selected_collection)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(subtitle__icontains=q) | Q(authors__name__icontains=q) |
                       Q(subjects__name__icontains=q) | Q(keywords__icontains=q) |
                       Q(editions__identifiers__value__icontains=q))
    if kind: qs = qs.filter(kind=kind)
    if language: qs = qs.filter(language=language)
    if len(year) <= 4 and year.isascii() and year.isdigit():
        qs = qs.filter(editions__year=int(year))
    qs = with_formats(qs)
    if fmt in {"digital", "ambos"}:
        qs = qs.filter(digital=True)
    if fmt in {"fisico", "ambos"}:
        qs = qs.filter(physical=True)
    languages = Work.objects.filter(state=Work.State.PUBLISHED).exclude(language="").order_by("language").values_list("language", flat=True).distinct()
    page = Paginator(qs.distinct().order_by("title", "pk"), 24).get_page(request.GET.get("page"))
    return render(request, "catalogue.html", {"page": page, "q": q, "kind": kind, "language": language,
                   "year": year, "format": fmt, "kinds": Work.Kind.choices, "languages": languages,
                   "collections": collections, "selected_collection": selected_collection})


@require(allowed)
def detail(request, pk):
    work = get_object_or_404(visible(), pk=pk)
    versions = Version.objects.filter(document__edition__work=work, state=Version.State.PUBLISHED).select_related("document__edition")
    copies = list(Copy.objects.filter(edition__work=work, state=Copy.State.LOCAL)
                  .select_related("location", "edition")
                  .order_by("location__name", "edition__label", "inventory"))
    saved = student(request.user) and SavedWork.objects.filter(user=request.user, work=work).exists()
    return render(request, "work.html", {"work": work, "versions": versions, "copies": copies, "saved": saved,
                                         "collections": work.collections.filter(published=True)})


@require(allowed)
@require_safe
@never_cache
def export_bibliography(request, pk, edition_pk, format):
    formats = {
        "ris": (as_ris, "application/x-research-info-systems"),
        "bib": (as_bibtex, "application/x-bibtex"),
    }
    if format not in formats:
        raise Http404
    edition = get_object_or_404(
        Edition.objects.select_related("work").prefetch_related(
            Prefetch("work__authors", queryset=Author.objects.order_by("pk")), "identifiers",
        ),
        pk=edition_pk, work_id=pk, work__state=Work.State.PUBLISHED,
    )
    render_entry, content_type = formats[format]
    return HttpResponse(render_entry(edition), content_type=f"{content_type}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="rovuma-{edition.pk}.{format}"'})


def cover_path(pk):
    return settings.PRIVATE_ROOT / "covers" / f"{pk}.webp"


@require(allowed)
def cover(request, pk):
    work = get_object_or_404(visible(), pk=pk)
    path = cover_path(work.pk)
    if work.is_demo and not path.is_file():
        marker = Identifier.objects.filter(edition__work=work, scheme=SCHEME, value__startswith=PREFIX).values_list("value", flat=True).first()
        key = marker.removeprefix(PREFIX).lower() if marker else ""
        if key in KEYS:
            path = asset(key, "webp")
    try:
        image = path.open("rb")
    except FileNotFoundError:
        from django.templatetags.static import static
        return redirect(static("cover-default.svg"))
    response = FileResponse(image, content_type="image/webp")
    response["Cache-Control"] = "private, no-store"
    return response


@require(student)
def library(request):
    recent = available_readings(Progress, request.user).order_by("-updated")[:50]
    bookmarks = available_readings(Bookmark, request.user).order_by("-created")[:100]
    saved = Work.objects.filter(state=Work.State.PUBLISHED, saved_entries__user=request.user)
    saved = saved.order_by("-saved_entries__created", "-pk")
    page = Paginator(saved, 24).get_page(request.GET.get("page"))
    return render(request, "library.html", {"recent": recent, "bookmarks": bookmarks, "page": page})


@require(student)
@require_POST
def save_work(request, pk):
    work = get_object_or_404(Work, pk=pk, state=Work.State.PUBLISHED)
    action = request.POST.get("action")
    if action == "save":
        SavedWork.objects.get_or_create(user=request.user, work=work)
        messages.success(request, "Obra guardada em Minhas leituras.")
    elif action == "remove":
        SavedWork.objects.filter(user=request.user, work=work).delete()
        messages.success(request, "Obra retirada da sua lista.")
        if request.POST.get("source") == "library":
            return redirect("library")
    else:
        raise Http404
    return redirect("work", pk=pk)


@permission(EDITOR)
def collection(request):
    q = request.GET.get("q", "").strip()[:150]
    state = request.GET.get("estado", "")
    works = Work.objects.all()
    if q:
        works = works.filter(title__icontains=q)
    if state in Work.State.values:
        works = works.filter(state=state)
    else:
        state = ""
    page = Paginator(works.order_by("-modified", "-pk"), 30).get_page(request.GET.get("page"))
    return render(request, "collection.html", {"page": page, "q": q, "state": state, "states": Work.State.choices})



class WorkForm(forms.ModelForm):
    cover_image = forms.FileField(label="Capa (JPEG, PNG ou WebP)", required=False)

    def clean_cover_image(self):
        uploaded = self.cleaned_data["cover_image"]
        if not uploaded:
            return None
        if uploaded.size > 5 * 1024**2:
            raise forms.ValidationError("A capa pode ter até 5 MiB.")
        try:
            with Image.open(uploaded, formats=("JPEG", "PNG", "WEBP")) as image:
                if image.width * image.height > 16_000_000:
                    raise forms.ValidationError("A imagem excede o limite de 16 megapíxeis.")
                image.thumbnail((600, 840))
                target = BytesIO()
                image.convert("RGB").save(target, "WEBP", quality=82)
                return target.getvalue()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise forms.ValidationError("Escolha uma imagem JPEG, PNG ou WebP válida.")

    class Meta:
        model = Work
        fields = ("title", "subtitle", "kind", "language", "summary", "keywords", "terms", "authors", "subjects", "collections")


@permission(EDITOR)
def edit_work(request, pk=None, upload_document=False):
    work = get_object_or_404(Work, pk=pk) if pk else None
    form = WorkForm(request.POST if request.method == "POST" else None, request.FILES, instance=work)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if work is None:
                    saved = form.save()
                else:
                    saved = form.save(commit=False)
                    fields = [name for name in WorkForm.Meta.fields if not Work._meta.get_field(name).many_to_many]
                    saved.save(update_fields=[*fields, "modified"])
                    form.save_m2m()
                if upload_document:
                    edition = Edition.objects.create(work=saved, label="1.ª edição")
                record(request.user, "collection", "Guardou obra", saved.pk)
                if form.cleaned_data["cover_image"]:
                    path = cover_path(saved.pk)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    fd, temporary = mkstemp(dir=path.parent)
                    try:
                        with os.fdopen(fd, "wb") as target:
                            target.write(form.cleaned_data["cover_image"])
                        os.replace(temporary, path)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
        except OSError as error:
            logger.error("Falha ao guardar a capa no armazenamento privado: errno %s.", error.errno)
            form.add_error("cover_image", "Não foi possível guardar a capa. Volte a seleccionar a imagem ou guarde a obra sem capa.")
        else:
            if upload_document:
                return redirect("upload", pk=edition.pk)
            return redirect("manage_work", pk=saved.pk)
    return render(request, "form.html", {"form": form, "heading": "Registar obra digital" if upload_document else "Dados da obra",
                                        "layout": "management/base.html", "submit": "Continuar para o carregamento" if upload_document else None})


@permission(EDITOR)
def manage_work(request, pk):
    work = get_object_or_404(Work.objects.prefetch_related("editions__copies", "editions__identifiers", "collections"), pk=pk)
    versions = Version.objects.filter(document__edition__work=work).select_related("document__edition", "job").order_by("-created")
    return render(request, "manage_work.html", {"work": work, "versions": versions})


@permission(EDITOR)
@require_POST
def work_state(request, pk):
    states = {"publish": Work.State.PUBLISHED, "withdraw": Work.State.DRAFT, "archive": Work.State.ARCHIVED}
    action = request.POST.get("action")
    if action not in states:
        raise Http404
    with transaction.atomic():
        work = get_object_or_404(Work.objects.select_for_update(), pk=pk)
        if action == "publish" and not has_consultable_format(work):
            messages.error(request, "Registe um exemplar para consulta local ou publique uma versão digital revista.")
        else:
            work.state = states[action]
            work.save(update_fields=["state", "modified"])
            record(request.user, "collection", "Alterou estado da obra", work.pk, state=work.state)
    return redirect("manage_work", pk=pk)


@permission(EDITOR)
def inventory(request):
    q = request.GET.get("q", "").strip()[:150]
    state = request.GET.get("estado", "")
    copies = Copy.objects.select_related("edition__work", "location")
    if q:
        copies = copies.filter(Q(inventory__icontains=q) | Q(edition__work__title__icontains=q)
                               | Q(location__name__icontains=q) | Q(location__unit__icontains=q)
                               | Q(location__room__icontains=q) | Q(location__shelf__icontains=q)
                               | Q(location__level__icontains=q))
    if state in Copy.State.values:
        copies = copies.filter(state=state)
    else:
        state = ""
    page = Paginator(copies.order_by("edition__work__title", "inventory"), 30).get_page(request.GET.get("page"))
    return render(request, "management/inventory.html", {"page": page, "q": q, "state": state, "states": Copy.State.choices})


@permission(EDITOR)
def locations(request):
    return render(request, "locations.html", {"locations": Location.objects.all(),
                  "authors": Author.objects.order_by("name"), "subjects": Subject.objects.order_by("name")})


@permission(EDITOR)
def manage_collections(request):
    collections = Collection.objects.order_by("name", "pk")
    page = Paginator(collections, 30).get_page(request.GET.get("page"))
    return render(request, "manage_collections.html", {"page": page})


class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ("name", "description", "published")


@permission(EDITOR)
def edit_collection(request, pk=None):
    collection = get_object_or_404(Collection, pk=pk) if pk else None
    form = CollectionForm(request.POST if request.method == "POST" else None, instance=collection)
    if form.is_valid():
        try:
            with transaction.atomic():
                item = form.save()
                record(request.user, "collection", "Guardou colecção", item.pk, published=item.published)
        except IntegrityError:
            form.add_error("name", "Já existe uma colecção com esse nome.")
        else:
            return redirect("manage_collections")
    return render(request, "form.html", {"form": form, "heading": "Editar colecção" if pk else "Nova colecção",
                                         "layout": "management/base.html", "submit": "Guardar colecção"})


@permission(EDITOR)
def edit_related(request, kind, parent=None, pk=None):
    definitions = {
        "edicao": (Edition, ("label", "publisher", "year"), "work", Work),
        "identificador": (Identifier, ("scheme", "value"), "edition", Edition),
        "exemplar": (Copy, ("inventory", "location", "state", "condition"), "edition", Edition),
        "localizacao": (Location, ("name", "unit", "room", "shelf", "level", "description"), None, None),
        "autor": (Author, ("name",), None, None),
        "assunto": (Subject, ("name",), None, None),
    }
    if kind not in definitions:
        raise Http404
    model, fields, relation, parent_model = definitions[kind]
    qs = model.objects.all()
    if relation:
        get_object_or_404(parent_model, pk=parent)
        qs = qs.filter(**{relation + "_id": parent})
    instance = get_object_or_404(qs, pk=pk) if pk else model()
    if relation and not pk:
        setattr(instance, relation + "_id", parent)
    Form = forms.modelform_factory(model, fields=fields)
    form = Form(request.POST if request.method == "POST" else None, instance=instance)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if model is Copy:
                    work = Work.objects.select_for_update().get(pk=instance.edition.work_id)
                item = form.save()
                record(request.user, "collection", "Guardou registo", item.pk, kind=kind)
                if model is Copy and unpublish_if_unavailable(work, request.user):
                    messages.warning(request, "A obra voltou a rascunho porque já não tem um formato consultável.")
            if kind == "edicao":
                return redirect("manage_work", pk=item.work_id)
            if relation:
                return redirect("manage_work", pk=item.edition.work_id)
            return redirect("locations")
        except IntegrityError:
            form.add_error(None, "Já existe um registo com esses dados.")
    return render(request, "form.html", {"form": form, "heading": "Registo do acervo", "layout": "management/base.html"})
