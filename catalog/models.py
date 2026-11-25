from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=200, unique=True)
    def __str__(self): return self.name


class Subject(models.Model):
    name = models.CharField(max_length=150, unique=True)
    def __str__(self): return self.name


class Collection(models.Model):
    name = models.CharField("Nome", max_length=180, unique=True)
    description = models.TextField("Descrição", blank=True)
    published = models.BooleanField("Visível no catálogo", default=False)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Work(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PUBLISHED = "published", "Publicada"
        ARCHIVED = "archived", "Arquivada"

    class Kind(models.TextChoices):
        BOOK = "book", "Livro"
        MANUAL = "manual", "Manual"
        MANUSCRIPT = "manuscript", "Manuscrito"
        THESIS = "thesis", "Trabalho académico"
        ARTICLE = "article", "Artigo"
        OTHER = "other", "Outro"

    title = models.CharField(max_length=300)
    subtitle = models.CharField(max_length=300, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.BOOK)
    language = models.CharField(max_length=80)
    summary = models.TextField(blank=True)
    keywords = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.DRAFT, db_index=True)
    authors = models.ManyToManyField(Author, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True)
    collections = models.ManyToManyField(Collection, related_name="works", blank=True, verbose_name="Colecções")
    is_demo = models.BooleanField(default=False, editable=False)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = (("manage_collection", "Gerir acervo"),)
        indexes = [models.Index(fields=("state", "title"), name="work_state_title_idx"),
                   models.Index(fields=("kind", "language"), name="work_kind_language_idx")]
    def __str__(self): return self.title


class Edition(models.Model):
    work = models.ForeignKey(Work, related_name="editions", on_delete=models.PROTECT)
    label = models.CharField(max_length=150)
    publisher = models.CharField(max_length=200, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    class Meta:
        indexes = [models.Index(fields=("year", "work"), name="edition_year_work_idx")]

    def __str__(self): return f"{self.work}: {self.label}"


class Identifier(models.Model):
    edition = models.ForeignKey(Edition, related_name="identifiers", on_delete=models.CASCADE)
    scheme = models.CharField(max_length=30)
    value = models.CharField(max_length=150)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("scheme", "value"), name="unique_bibliographic_identifier")]


class Location(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    unit = models.CharField("Biblioteca ou unidade", max_length=160, blank=True)
    room = models.CharField("Sala", max_length=80, blank=True)
    shelf = models.CharField("Estante", max_length=80, blank=True)
    level = models.CharField("Prateleira", max_length=80, blank=True)

    @property
    def placement(self):
        return " · ".join(filter(None, (self.unit, self.room, self.shelf, self.level)))

    def __str__(self): return self.name


class Copy(models.Model):
    class State(models.TextChoices):
        LOCAL = "local", "Consulta local"
        MAINTENANCE = "maintenance", "Em manutenção"
        UNAVAILABLE = "unavailable", "Indisponível"
        REMOVED = "removed", "Retirado"
    edition = models.ForeignKey(Edition, related_name="copies", on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    condition = models.CharField("Condição de conservação", max_length=160, blank=True)
    inventory = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.LOCAL)
