from .models import Work


RIS_TYPES = {
    Work.Kind.BOOK: "BOOK",
    Work.Kind.MANUAL: "MANUAL",
    Work.Kind.MANUSCRIPT: "MANSCPT",
    Work.Kind.THESIS: "THES",
    Work.Kind.ARTICLE: "JOUR",
}

BIBTEX_TYPES = {Work.Kind.BOOK: "book", Work.Kind.MANUAL: "manual", Work.Kind.ARTICLE: "article"}
BIBTEX_ESCAPE = str.maketrans({
    "\\": r"\textbackslash{}", "{": r"\textbraceleft{}", "}": r"\textbraceright{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
})


def single_line(value):
    return " ".join(str(value).split())


def identifiers(edition, scheme):
    for identifier in edition.identifiers.all():
        if identifier.scheme.strip().lower() == scheme and identifier.value.strip():
            yield single_line(identifier.value)


def bibliography_doi(edition):
    doi = next(identifiers(edition, "doi"), "")
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            return doi[len(prefix):].strip()
    return doi


def full_title(work):
    return f"{work.title}: {work.subtitle}" if work.subtitle else work.title


def as_ris(edition):
    work = edition.work
    fields = [
        ("TY", RIS_TYPES.get(work.kind, "GEN")),
        ("TI", full_title(work)),
        *(("AU", author.name) for author in work.authors.all()),
        ("PY", edition.year),
        ("ET", edition.label),
        ("PB", edition.publisher),
        ("LA", work.language),
        ("DO", bibliography_doi(edition)),
        *(("SN", value) for value in identifiers(edition, "isbn")),
        *(("SN", value) for value in identifiers(edition, "issn")),
    ]
    return "".join(f"{tag}  - {single_line(value)}\r\n" for tag, value in fields if value) + "ER  - \r\n"


def as_bibtex(edition):
    work = edition.work
    authors = [single_line(author.name).translate(BIBTEX_ESCAPE) for author in work.authors.all()]
    fields = {
        "title": full_title(work),
        "year": edition.year,
        "edition": edition.label,
        "publisher": edition.publisher,
        "language": work.language,
        "doi": bibliography_doi(edition),
        "isbn": next(identifiers(edition, "isbn"), ""),
        "issn": next(identifiers(edition, "issn"), ""),
    }
    lines = [f"@{BIBTEX_TYPES.get(work.kind, 'misc')}{{rovuma-{edition.pk},"]
    if authors:
        # Names are stored as display strings. Group names which contain BibTeX's separator.
        names = " and ".join(f"{{{name}}}" if " and " in name else name for name in authors)
        lines.append(f"  author = {{{names}}},")
    for key, value in fields.items():
        if value:
            escaped = single_line(value).translate(BIBTEX_ESCAPE)
            if key == "title":
                escaped = f"{{{escaped}}}"
            lines.append(f"  {key} = {{{escaped}}},")
    lines.append("}")
    return "\n".join(lines) + "\n"
