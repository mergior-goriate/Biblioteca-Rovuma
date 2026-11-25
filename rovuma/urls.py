from django.contrib.auth import views as auth
from django.http import HttpResponsePermanentRedirect
from django.urls import path, re_path, reverse_lazy

from accounts import views as account
from audit.views import events
from catalog import views as catalog
from documents import views as document
from reading import views as reading
from management import views as management


def redirect_legacy_management(request, route=None):
    target = "/admin/" + (route or "")
    query = request.get_full_path().partition("?")[2]
    if query:
        target += "?" + query
    return HttpResponsePermanentRedirect(target, preserve_request=True)


urlpatterns = [
    path("", catalog.home, name="home"),
    path("portal/", catalog.portal, name="portal"),
    path("entrar/", account.LocalLogin.as_view(), name="login"),
    path("sair/", account.sign_out, name="logout"),
    path("conta/activar/<str:token>/", account.activate, name="activate"),
    path("conta/recuperar/", account.LocalReset.as_view(), name="password_reset"),
    path("conta/recuperar/enviado/", auth.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("conta/recuperar/<uidb64>/<token>/", auth.PasswordResetConfirmView.as_view(token_generator=account.ResetToken()), name="password_reset_confirm"),
    path("conta/recuperar/concluido/", auth.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("conta/senha/", account.LocalChange.as_view(), name="password_change"),
    path("conta/senha/guardada/", auth.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("perfil/", account.profile, name="profile"),
    path("catalogo/", catalog.catalogue, name="catalogue"),
    path("obra/<int:pk>/", catalog.detail, name="work"),
    path("obra/<int:pk>/capa/", catalog.cover, name="cover"),
    path("obra/<int:pk>/edicao/<int:edition_pk>/exportar/<slug:format>/", catalog.export_bibliography, name="work_bibliography"),
    path("obra/<int:pk>/guardar/", catalog.save_work, name="save_work"),
    path("leituras/", catalog.library, name="library"),
    path("ler/<uuid:pk>/", reading.reader, name="reader"),
    path("ler/<uuid:pk>/progresso/", reading.update, name="reading_update"),
    path("documento/<uuid:pk>/pdf/", document.pdf, name="pdf"),
    path("documento/<uuid:pk>/descarregar/", document.download, name="download"),
    path("admin/palavra-passe/", account.LocalChange.as_view(management_area=True, success_url=reverse_lazy("management")), name="management_password"),
    path("admin/entrar/", account.ManagementLogin.as_view(), name="management_login"),
    path("admin/pre-visualizar/<uuid:pk>/", reading.preview, name="reader_preview"),
    path("admin/", management.dashboard, name="management"),
    path("admin/documentos/", management.document_queue, name="document_queue"),
    path("admin/obras/", catalog.collection, name="collection"),
    path("admin/obras/nova/", catalog.edit_work, name="new_work"),
    path("admin/obras/nova/digital/", catalog.edit_work, {"upload_document": True}, name="new_digital_work"),
    path("admin/obras/<int:pk>/", catalog.manage_work, name="manage_work"),
    path("admin/obras/<int:pk>/editar/", catalog.edit_work, name="edit_work"),
    path("admin/obras/<int:pk>/estado/", catalog.work_state, name="work_state"),
    path("admin/coleccoes/", catalog.manage_collections, name="manage_collections"),
    path("admin/coleccoes/nova/", catalog.edit_collection, name="new_collection"),
    path("admin/coleccoes/<int:pk>/editar/", catalog.edit_collection, name="edit_collection"),
    path("admin/exemplares/", catalog.inventory, name="inventory"),
    path("admin/localizacoes/", catalog.locations, name="locations"),
    path("admin/registo/<slug:kind>/", catalog.edit_related, name="new_location"),
    path("admin/registo/<slug:kind>/editar/<int:pk>/", catalog.edit_related, name="edit_location"),
    path("admin/registo/<slug:kind>/<int:parent>/", catalog.edit_related, name="new_related"),
    path("admin/registo/<slug:kind>/<int:parent>/<int:pk>/", catalog.edit_related, name="edit_related"),
    path("admin/carregar/<int:pk>/", document.upload_page, name="upload"),
    path("admin/carregar/<int:pk>/iniciar/", document.start_upload, name="start_upload"),
    path("admin/partes/<uuid:upload_id>/", document.chunks, name="upload_chunks"),
    path("admin/documento/<uuid:pk>/", document.editorial, name="editorial"),
    path("admin/estudantes/", account.students, name="students"),
    path("admin/estudantes/<int:pk>/", account.credential, name="credential"),
    path("admin/estudantes/<int:pk>/corrigir/", account.correct, name="correct"),
    path("admin/importar/", account.imports, name="imports"),
    path("admin/importar/<int:pk>/", account.import_preview, name="import_preview"),
    path("admin/auditoria/", events, name="audit"),
    re_path(r"^gestao(?:/(?P<route>.*))?$", redirect_legacy_management),
]
