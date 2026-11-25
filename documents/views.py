import os
import re
import shutil
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST, require_http_methods

from accounts.access import EDITOR, has, permission, require, student
from audit.models import record
from catalog.availability import unpublish_if_unavailable
from catalog.models import Edition, Work
from .formats import SUPPORTED_FORMATS, TEXT_MAX_BYTES
from .models import Document, Job, Licence, Upload, Version
from .storage import original, original_file, part, reading_pdf


class UploadForm(forms.Form):
    mode = forms.ChoiceField(label="Modalidade de acesso", choices=Version.Mode.choices)
    authorization = forms.CharField(label="Licença ou referência da autorização", max_length=3000, widget=forms.Textarea(attrs={"rows": 4}))


def data_error(message, status=400, **extra):
    return JsonResponse({"error": message, **extra}, status=status)


@permission(EDITOR)
def upload_page(request, pk):
    edition = get_object_or_404(Edition.objects.select_related("work"), pk=pk)
    return render(request, "upload.html", {
        "edition": edition, "form": UploadForm(), "limit": settings.UPLOAD_MAX_BYTES,
        "accept": ",".join(f".{extension}" for extension in SUPPORTED_FORMATS),
        "text_limit": min(TEXT_MAX_BYTES, settings.UPLOAD_MAX_BYTES),
    })


@permission(EDITOR)
@require_POST
def start_upload(request, pk):
    edition = get_object_or_404(Edition, pk=pk)
    form = UploadForm(request.POST)
    name = Path(request.POST.get("name", "").replace(chr(92), "/")).name
    format_ = Path(name).suffix[1:].lower()
    try:
        size = int(request.POST.get("size", "0"))
    except ValueError:
        return data_error("Tamanho inválido.")
    if not form.is_valid():
        return data_error("Indique a modalidade de acesso e a autorização.")
    if format_ not in SUPPORTED_FORMATS or len(name) > 180 or any(ord(c) < 32 for c in name):
        return data_error("Escolha um ficheiro PDF, DOCX, ODT ou TXT com um nome válido.")
    if not 0 < size <= settings.UPLOAD_MAX_BYTES:
        return data_error("O tamanho excede o limite configurado ou o ficheiro está vazio.")
    if format_ == "txt" and size > TEXT_MAX_BYTES:
        return data_error("Os ficheiros TXT podem ter até 10 MiB.")
    settings.PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(settings.PRIVATE_ROOT).free < size + settings.DISK_RESERVE_BYTES:
        return data_error("O servidor tem espaço insuficiente.", 507)
    upload = Upload.objects.create(owner=request.user, edition=edition, name=name, size=size,
                                   mode=form.cleaned_data["mode"], authorization=form.cleaned_data["authorization"])
    return JsonResponse({"url": reverse("upload_chunks", args=[upload.pk]), "chunk": settings.UPLOAD_CHUNK_BYTES}, status=201)


@permission(EDITOR)
@require_http_methods(["GET", "POST"])
def chunks(request, upload_id):
    with transaction.atomic():
        upload = get_object_or_404(Upload.objects.select_for_update(), pk=upload_id, owner=request.user)
        if request.method == "GET":
            return JsonResponse({"offset": upload.offset, "size": upload.size, "complete": bool(upload.version_id),
                                 "chunk": settings.UPLOAD_CHUNK_BYTES})
        if upload.version_id:
            return JsonResponse({"offset": upload.size, "complete": True,
                                 "next": reverse("manage_work", args=[upload.edition.work_id])})
        if request.POST.get("finish") == "1":
            if upload.offset != upload.size or not part(upload_id).is_file():
                return data_error("O carregamento ainda está incompleto.", 409, offset=upload.offset)
            document, _ = Document.objects.get_or_create(edition=upload.edition)
            version = Version.objects.create(document=document, file_format=Path(upload.name).suffix.lower()[1:],
                                             original_name=upload.name, access_mode=upload.mode, authorization=upload.authorization)
            dest = original(version.pk)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.link(part(upload_id), dest)
            Job.objects.create(version=version)
            Licence.objects.create(version=version, recorded_by=request.user, reference=upload.authorization)
            upload.version = version
            upload.save(update_fields=["version", "updated"])
            record(request.user, "collection", "Recebeu documento para análise", version.pk, edition=upload.edition_id)
            transaction.on_commit(lambda: part(upload_id).unlink(missing_ok=True))
            messages.success(request, "Ficheiro recebido. Aguarda análise na fila de documentos.")
            return JsonResponse({"offset": upload.size, "complete": True,
                                 "next": reverse("manage_work", args=[upload.edition.work_id])})
        payload = request.FILES.get("chunk")
        try:
            offset = int(request.POST.get("offset", "-1"))
        except ValueError:
            offset = -1
        if offset != upload.offset:
            return data_error("O servidor já confirmou outra posição. Retome o carregamento.", 409, offset=upload.offset)
        if not payload or not 0 < payload.size <= min(settings.UPLOAD_CHUNK_BYTES, upload.size - offset):
            return data_error("Parte inválida ou demasiado grande.")
        path = part(upload_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(path.parent).free < payload.size + settings.DISK_RESERVE_BYTES:
            return data_error("Terá de libertar espaço no servidor para retomar.", 507)
        if not path.exists() and offset:
            return data_error("O ficheiro parcial deixou de estar disponível.", 410)
        with path.open("r+b" if path.exists() else "w+b") as fp:
            if fp.seek(0, os.SEEK_END) < offset:
                return data_error("O ficheiro parcial está incompleto.", 410)
            fp.seek(offset)
            fp.truncate()
            for block in payload.chunks():
                fp.write(block)
            fp.flush()
            os.fsync(fp.fileno())
        upload.offset += payload.size
        upload.save(update_fields=["offset", "updated"])
        return JsonResponse({"offset": upload.offset})


def version_for(user, pk):
    versions = Version.objects.select_related("document__edition__work", "job")
    if has(user, EDITOR):
        versions = versions.filter(state__in=[Version.State.REVIEW, Version.State.PUBLISHED, Version.State.ARCHIVED],
                                   job__state=Job.State.DONE, pages__gt=0)
    elif student(user):
        versions = versions.filter(state=Version.State.PUBLISHED, document__edition__work__state=Work.State.PUBLISHED)
    else:
        raise PermissionDenied
    return get_object_or_404(versions, pk=pk)


def read_permission(user):
    return bool(student(user) or has(user, EDITOR))


def stream_range(path, request):
    size = path.stat().st_size
    header = request.headers.get("Range")
    if not header:
        return FileResponse(path.open("rb"), content_type="application/pdf")
    match = re.fullmatch(r"bytes=(\d{0,18})-(\d{0,18})", header, flags=re.ASCII)
    if match and any(match.groups()):
        left, right = match.groups()
        start = int(left) if left else max(0, size - int(right))
        end = min(size - 1, int(right)) if left and right else size - 1
        if start <= end:
            from django.http import StreamingHttpResponse

            def blocks():
                with path.open("rb") as file:
                    file.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        data = file.read(min(64 * 1024, remaining))
                        if not data:
                            break
                        yield data
                        remaining -= len(data)

            response = StreamingHttpResponse(blocks() if request.method != "HEAD" else (), status=206, content_type="application/pdf")
            response["Content-Length"] = str(end - start + 1)
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
            return response
    return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})


@require(read_permission)
@require_http_methods(["GET", "HEAD"])
def pdf(request, pk):
    version = version_for(request.user, pk)
    path = reading_pdf(version)
    if not path.is_file():
        raise Http404
    response = stream_range(path, request)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, no-store"
    if response.status_code in (200, 206):
        response["Content-Disposition"] = content_disposition_header(False, "leitura.pdf")
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@require(read_permission)
@require_http_methods(["GET", "HEAD"])
def download(request, pk):
    version = version_for(request.user, pk)
    if version.access_mode != Version.Mode.DOWNLOAD or version.state != Version.State.PUBLISHED:
        raise PermissionDenied
    path = original_file(version)
    if not path.is_file():
        raise Http404
    response = FileResponse(path.open("rb"), as_attachment=True, filename=version.original_name,
                            content_type="application/octet-stream")
    response["Cache-Control"] = "private, no-store"
    return response


@permission(EDITOR)
@require_POST
def editorial(request, pk):
    action = request.POST.get("action")
    with transaction.atomic():
        unlocked = get_object_or_404(Version.objects.select_related("document__edition"), pk=pk)
        work = Work.objects.select_for_update().get(pk=unlocked.document.edition.work_id)
        job = Job.objects.select_for_update().get(version_id=pk)
        version = Version.objects.select_for_update().get(pk=pk)
        if action == "publish":
            if (version.state not in {Version.State.REVIEW, Version.State.ARCHIVED} or job.state != Job.State.DONE
                    or not version.pages or not version.sha256 or not version.authorization.strip()
                    or not Licence.objects.filter(version=version).exclude(reference="").exists()
                    or not reading_pdf(version).is_file() or not original_file(version).is_file()
                    or request.POST.get("checked") != "yes"):
                messages.error(request, "A publicação requer análise concluída, autorização e confirmação da revisão.")
                return redirect("manage_work", pk=work.pk)
            previous = Version.objects.filter(document=version.document, state=Version.State.PUBLISHED)
            for old in previous:
                record(request.user, "collection", "Arquivou versão substituída", old.pk, replacement=str(pk))
            previous.update(state=Version.State.ARCHIVED)
            version.state = Version.State.PUBLISHED
            work.state = Work.State.PUBLISHED
            work.save(update_fields=["state", "modified"])
            label = "Publicou versão"
        elif action in {"archive", "withdraw"} and version.state == Version.State.PUBLISHED:
            version.state = Version.State.ARCHIVED if action == "archive" else Version.State.REVIEW
            label = "Arquivou versão" if action == "archive" else "Retirou versão"
        elif action == "retry" and job.state == Job.State.ERROR:
            import uuid
            job.run, job.state, job.error = uuid.uuid4(), Job.State.WAITING, ""
            job.save()
            label = "Reagendou processamento"
        else:
            raise Http404
        version.save(update_fields=["state"])
        record(request.user, "collection", label, version.pk)
        if action in {"archive", "withdraw"} and unpublish_if_unavailable(work, request.user):
            messages.warning(request, "A obra voltou a rascunho porque já não tem um formato consultável.")
    return redirect("manage_work", pk=work.pk)
