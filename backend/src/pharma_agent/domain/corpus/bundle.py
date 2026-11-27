"""Knowledge bundle ``knowledge-bundle/v1`` (spec C §5): models, encoding and validation.

Public API: the models, ``BUNDLE_SCHEMA_VERSION``, ``model_slug``, ``encode_vector`` and
``decode_vector``, and the checks that work on content already read. The bundle files are
read and written by ``pharma_agent.infrastructure.corpus.bundle_files``: pharma-lab builds a
``KnowledgeBundle``, calls ``write_bundle`` and then adds each model's vectors with
``write_bundle_embeddings``; the backend import calls ``read_bundle`` and loads the vectors
of its model with ``read_bundle_embeddings``. Both sides run the same checks, defined here.
Embedding files are checked line by line (``EmbeddingFileCheck``), so memory holds at most
one model's vectors however many models a bundle ships.
"""

import base64
import binascii
import hashlib
import json
import re
import struct
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from pharma_agent.domain.shared.errors import DomainError

BUNDLE_SCHEMA_VERSION: Final = "knowledge-bundle/v1"
MANIFEST_FILE: Final = "manifest.json"
DOCUMENTS_FILE: Final = "documents.jsonl"
SECTIONS_FILE: Final = "sections.jsonl"
GLOSSARY_FILE: Final = "glossary.json"
COLLOQUIAL_MAPPINGS_FILE: Final = "colloquial_mappings.json"
EMBEDDINGS_DIR: Final = "embeddings"
REQUIRED_FILES: Final = (
    DOCUMENTS_FILE,
    SECTIONS_FILE,
    GLOSSARY_FILE,
    COLLOQUIAL_MAPPINGS_FILE,
)

_STRICT = ConfigDict(extra="forbid", strict=True)
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DocumentKind(StrEnum):
    """What a bundle document is: a drug monograph, a general monograph or a leaflet."""

    DRUG_MONOGRAPH = "drug_monograph"
    GENERAL_MONOGRAPH = "general_monograph"
    LEAFLET = "leaflet"


class BlockKind(StrEnum):
    """How a block's markdown is laid out."""

    PROSE = "prose"
    TABLE = "table"
    LIST = "list"
    INDEX_ENTRIES = "index_entries"


class SourceInfo(BaseModel):
    """Where a document comes from: a title and an optional URL."""

    model_config = _STRICT

    title: str
    url: str | None = None


class DocumentRecord(BaseModel):
    """One line of ``documents.jsonl``; `key` is unique within the bundle."""

    model_config = _STRICT

    key: str
    kind: DocumentKind
    title: str
    source: SourceInfo
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class BlockRecord(BaseModel):
    """A run of markdown inside a section, with optional source pages."""

    model_config = _STRICT

    kind: BlockKind
    markdown: str
    start_page: int | None = None
    end_page: int | None = None
    table_key: str | None = None


class SectionRecord(BaseModel):
    """One line of ``sections.jsonl``.

    `key` is unique within the bundle, `document_key` names a document and `ordinal`
    is unique within that document; `blocks` must not be empty.
    """

    model_config = _STRICT

    key: str
    document_key: str
    heading: str
    context_path: list[str]
    ordinal: int
    start_page: int | None = None
    end_page: int | None = None
    blocks: list[BlockRecord]


class GlossaryEntry(BaseModel):
    """One row of ``data/sources/term_glossary.json``."""

    model_config = _STRICT

    term: str
    case_sensitive: bool = False
    vietnamese_expansions: list[str] = Field(default_factory=list)
    english_expansions: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    category: str = ""
    confidence: str = ""
    source: str = ""


class ColloquialMappingRecord(BaseModel):
    """Colloquial names attached to sections.

    ``key`` is the curated leaflet slug from ``data/sources/colloquial_mappings.json``
    or, for a leaflet that only has title-derived product names, the leaflet slug; it
    may also be empty. It is copied into ``ColloquialMapping.key`` and never affects
    embedding text, term annotations or chunk version ids.
    """

    model_config = _STRICT

    key: str
    aliases: list[str] = Field(default_factory=list)
    visual_sign: str = ""
    product_names: list[str] = Field(default_factory=list)
    section_keys: list[str] = Field(default_factory=list)


class BundleCollection(BaseModel):
    """The collection a bundle fills."""

    model_config = _STRICT

    key: str
    title: str


class BundleGenerator(BaseModel):
    """The tool and build that produced a bundle."""

    model_config = _STRICT

    name: str
    version: str
    build_id: str


class BundleFile(BaseModel):
    """Size in bytes and sha256 hex digest of one bundle file."""

    model_config = _STRICT

    sha256: str
    bytes: int


class BundleEmbeddingFile(BaseModel):
    """The embedding file of one model and the dimension of its vectors."""

    model_config = _STRICT

    model: str
    dims: int
    file: str


# A chunk grows by whole sections until the next one would pass this; packed chunks
# average about 1,000 Qwen3 tokens on the corpus (measured, spec v2 §3.0c).
TARGET_CHUNK_CHARS = 4200
# A single section longer than this is split on its own. Tables and lists take more
# tokens per character than prose, so the longest chunk reaches about 3,200 tokens,
# inside the 4,096-token embedding slot and rerank ubatch.
MAX_CHUNK_CHARS = 5600


class BundleChunking(BaseModel):
    """How the chunker packs this bundle's sections.

    The default is the packed reading unit; target_chars=1 gives every section its own
    chunk (spec v2 §4.D, D7), and enrichment=False indexes the chunk text without
    header, colloquial names or term expansions (D2).
    """

    model_config = _STRICT

    target_chars: int = Field(default=TARGET_CHUNK_CHARS, gt=0)
    max_chars: int = Field(default=MAX_CHUNK_CHARS, gt=0)
    # Left out of the manifest and the content digest while on, so bundles written
    # before the switch existed keep their files and their release identity.
    enrichment: bool = Field(default=True, exclude_if=lambda enabled: enabled)

    @model_validator(mode="after")
    def _target_within_max(self) -> "BundleChunking":
        if self.target_chars > self.max_chars:
            raise ValueError("target_chars must not exceed max_chars")
        return self


class BundleManifest(BaseModel):
    """Contents of ``manifest.json``: identity, counts, file digests and chunking."""

    model_config = _STRICT

    schema_version: Literal["knowledge-bundle/v1"]
    collection: BundleCollection
    generator: BundleGenerator
    source_digests: dict[str, str]
    document_count: int
    section_count: int
    files: dict[str, BundleFile]
    embeddings: list[BundleEmbeddingFile] = Field(default_factory=list)
    chunking: BundleChunking = Field(default_factory=BundleChunking)


class KnowledgeBundle(BaseModel):
    """The manifest and knowledge content; vectors stay in the embedding files."""

    model_config = _STRICT

    manifest: BundleManifest
    documents: list[DocumentRecord]
    sections: list[SectionRecord]
    glossary: list[GlossaryEntry]
    colloquial_mappings: list[ColloquialMappingRecord]


class BundleValidationError(DomainError):
    """A bundle failed validation; `problems` lists every problem found."""

    code = "BUNDLE_INVALID"
    problems: list[str]

    def __init__(self, problems: Sequence[str]) -> None:
        """Keep `problems` and put them all in the message, one per line."""
        self.problems = list(problems)
        super().__init__("knowledge bundle is invalid:\n" + "\n".join(self.problems))


def model_slug(model: str) -> str:
    """File-name-safe slug of `model`: lowercase letters and digits joined by ``_``."""
    return _SLUG_RE.sub("_", model.lower()).strip("_")


def encode_vector(values: Sequence[float]) -> str:
    """Base64 of `values` packed as little-endian float32."""
    return base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode("ascii")


def decode_vector(data: str, dims: int) -> list[float]:
    """Inverse of ``encode_vector``.

    Raises:
        ValueError: `data` is not valid base64 or does not hold `dims` floats.
    """
    return list(struct.unpack(f"<{dims}f", _vector_bytes(data, dims)))


class _EmbeddingLine(BaseModel):
    model_config = _STRICT

    embedding_text_sha256: str = Field(pattern=_SHA256_RE.pattern)
    dims: int
    vector: str


_GLOSSARY_ADAPTER = TypeAdapter(list[GlossaryEntry])
_MAPPINGS_ADAPTER = TypeAdapter(list[ColloquialMappingRecord])


def missing_file_problem(name: str) -> str:
    """The problem reported when the bundle file `name` does not exist."""
    return f"{name}: file is missing"


def embedding_file_name(model: str) -> str:
    """Bundle-relative path of the embedding file of `model`."""
    return f"{EMBEDDINGS_DIR}/{model_slug(model)}.jsonl"


def parse_manifest(data: bytes) -> BundleManifest:
    """Validate the content of ``manifest.json``.

    Raises:
        BundleValidationError: `data` is not a valid manifest.
    """
    try:
        return BundleManifest.model_validate_json(data)
    except ValidationError as error:
        raise BundleValidationError(
            _validation_problems(MANIFEST_FILE, error)
        ) from error


def manifest_json(manifest: BundleManifest) -> str:
    """Text of ``manifest.json`` for `manifest`."""
    return manifest.model_dump_json(indent=2) + "\n"


@dataclass(frozen=True)
class ListedFile:
    """A file the manifest lists, with what a reader must check about it.

    Attributes:
        name: Bundle-relative path of the file.
        expected: Size and digest the manifest declares.
        problem: Set when the file is not part of the schema; it is then not read.
        content: True for a content file, False for an embedding file.
        dims: Vector dimension of an embedding file whose entry is valid, else None.
    """

    name: str
    expected: BundleFile
    problem: str | None
    content: bool
    dims: int | None


def listed_files(manifest: BundleManifest, problems: list[str]) -> list[ListedFile]:
    """Check the manifest's entries and return its files in manifest order.

    Problems of the embedding entries and missing required entries go to `problems`.
    """
    expected_embedding_files, embedding_dims = _embedding_entries(manifest, problems)
    problems.extend(
        f"{MANIFEST_FILE}: files.{name}: missing entry"
        for name in REQUIRED_FILES
        if name not in manifest.files
    )
    listed: list[ListedFile] = []
    for name, expected in manifest.files.items():
        content = name in REQUIRED_FILES
        problem = None
        if not content and name not in expected_embedding_files:
            problem = (
                f"{MANIFEST_FILE}: files.{name}: not part of {BUNDLE_SCHEMA_VERSION}"
            )
        listed.append(
            ListedFile(name, expected, problem, content, embedding_dims.get(name))
        )
    return listed


def content_text(
    name: str, data: bytes, expected: BundleFile, problems: list[str]
) -> str | None:
    """Check a content file's digest and return its text, or None if it is not UTF-8."""
    problems.extend(
        digest_problems(name, len(data), hashlib.sha256(data).hexdigest(), expected)
    )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(f"{name}: file is not valid UTF-8")
        return None


def assemble_bundle(
    manifest: BundleManifest,
    texts: Mapping[str, str],
    problems: list[str],
    line_problems: Sequence[str],
) -> KnowledgeBundle:
    """Parse and cross-check the content files' `texts` into a bundle.

    `problems` holds the problems found so far and `line_problems` those of the
    embedding files, reported last.

    Raises:
        BundleValidationError: any problem was found, listing all of them.
    """
    documents = _parse_jsonl(
        DOCUMENTS_FILE, texts.get(DOCUMENTS_FILE, ""), DocumentRecord, problems
    )
    sections = _parse_jsonl(
        SECTIONS_FILE, texts.get(SECTIONS_FILE, ""), SectionRecord, problems
    )
    glossary = _parse_json_list(
        GLOSSARY_FILE, texts.get(GLOSSARY_FILE), _GLOSSARY_ADAPTER, problems
    )
    mappings = _parse_json_list(
        COLLOQUIAL_MAPPINGS_FILE,
        texts.get(COLLOQUIAL_MAPPINGS_FILE),
        _MAPPINGS_ADAPTER,
        problems,
    )
    for name, field, expected in (
        (DOCUMENTS_FILE, "document_count", manifest.document_count),
        (SECTIONS_FILE, "section_count", manifest.section_count),
    ):
        if name in texts and expected != _record_count(texts[name]):
            problems.append(
                f"{MANIFEST_FILE}: {field}: {expected} does not match "
                f"{name} ({_record_count(texts[name])} records)"
            )
    problems.extend(_content_problems(documents, sections, glossary, mappings))
    problems.extend(line_problems)

    if problems:
        raise BundleValidationError(problems)
    return KnowledgeBundle(
        manifest=manifest,
        documents=[record for _, record in documents],
        sections=[record for _, record in sections],
        glossary=glossary,
        colloquial_mappings=mappings,
    )


def declared_embedding_file(
    manifest: BundleManifest, model: str, dims: int
) -> tuple[str, BundleFile] | None:
    """Name and expected digest of the embedding file of `model` with `dims`.

    None when `manifest` declares no embeddings for `model` with `dims`.

    Raises:
        BundleValidationError: the embeddings are declared but the file is not listed.
    """
    if not any(
        (entry.model, entry.dims) == (model, dims) for entry in manifest.embeddings
    ):
        return None
    name = embedding_file_name(model)
    expected = manifest.files.get(name)
    if expected is None:
        raise BundleValidationError(
            [f"{MANIFEST_FILE}: files.{name}: missing entry for {model!r}"]
        )
    return name, expected


class EmbeddingFileCheck:
    """Size, sha256 and line checks of one embedding file, fed its raw lines in order.

    Lines are validated only when `dims` is known; `keep` receives the hash and vector
    of every valid line.
    """

    def __init__(
        self,
        name: str,
        dims: int | None,
        problems: list[str],
        keep: Callable[[str, list[float]], None] | None = None,
    ) -> None:
        """Report line problems of the file `name` to `problems`."""
        self._name = name
        self._dims = dims
        self._problems = problems
        self._keep = keep
        self._digest = hashlib.sha256()
        self._size = 0
        self._first_lines: dict[str, int] = {}
        self._utf8 = True

    def add(self, line_number: int, raw: bytes) -> None:
        """Account for line `line_number` (1-based) and check it."""
        self._digest.update(raw)
        self._size += len(raw)
        if self._dims is None or not self._utf8 or not raw.strip():
            return
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._problems.append(f"{self._name}: file is not valid UTF-8")
            self._utf8 = False
            return
        self._check_line(line_number, line, self._dims)

    def digest_problems(self, expected: BundleFile) -> list[str]:
        """Problems of the lines added so far against the manifest's `expected`."""
        return digest_problems(
            self._name, self._size, self._digest.hexdigest(), expected
        )

    def _check_line(self, line_number: int, line: str, dims: int) -> None:
        where = f"{self._name}:{line_number}"
        try:
            record = _EmbeddingLine.model_validate_json(line)
        except ValidationError as error:
            self._problems.extend(_validation_problems(where, error))
            return
        sha = record.embedding_text_sha256
        if record.dims != dims:
            self._problems.append(
                f"{where}: dims: {record.dims} does not match manifest dims {dims}"
            )
        elif sha in self._first_lines:
            self._problems.append(
                f"{where}: embedding_text_sha256: duplicate of line "
                f"{self._first_lines[sha]}"
            )
        else:
            self._first_lines[sha] = line_number
            try:
                vector = _vector_bytes(record.vector, dims)
            except ValueError as error:
                self._problems.append(f"{where}: vector: {error}")
                return
            if self._keep is not None:
                self._keep(sha, list(struct.unpack(f"<{dims}f", vector)))


def encode_bundle(bundle: KnowledgeBundle) -> tuple[BundleManifest, dict[str, bytes]]:
    """Validate `bundle`; return its manifest with computed digests and file contents.

    The manifest lists no embeddings.

    Raises:
        BundleValidationError: the content is invalid, listing every problem.
    """
    problems = _content_problems(
        list(enumerate(bundle.documents, start=1)),
        list(enumerate(bundle.sections, start=1)),
        bundle.glossary,
        bundle.colloquial_mappings,
    )
    if problems:
        raise BundleValidationError(problems)
    payloads: dict[str, bytes] = {
        DOCUMENTS_FILE: _jsonl_bytes(bundle.documents),
        SECTIONS_FILE: _jsonl_bytes(bundle.sections),
        GLOSSARY_FILE: _json_list_bytes(bundle.glossary),
        COLLOQUIAL_MAPPINGS_FILE: _json_list_bytes(bundle.colloquial_mappings),
    }
    manifest = BundleManifest(
        schema_version=bundle.manifest.schema_version,
        collection=bundle.manifest.collection,
        generator=bundle.manifest.generator,
        source_digests=dict(bundle.manifest.source_digests),
        document_count=len(bundle.documents),
        section_count=len(bundle.sections),
        files={
            name: BundleFile(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            for name, data in payloads.items()
        },
        chunking=bundle.manifest.chunking,
    )
    return manifest, payloads


def embedding_target(manifest: BundleManifest, model: str) -> str:
    """Name of the embedding file that `model` may write into the bundle of `manifest`.

    Raises:
        BundleValidationError: the model has no slug or its slug is another model's.
    """
    where = f"embeddings[{model!r}]"
    if not model_slug(model):
        raise BundleValidationError(
            [f"{where}: model name must contain letters or digits"]
        )
    name = embedding_file_name(model)
    for entry in manifest.embeddings:
        if entry.model != model and embedding_file_name(entry.model) == name:
            raise BundleValidationError(
                [f"{where}: model slug collides with {entry.model!r}"]
            )
    return name


class EmbeddingLineEncoder:
    """Encodes the (embedding_text_sha256, vector) pairs of one model as file lines.

    Pairs must be sorted by hash without duplicates; after the first bad pair no more
    lines are produced, and ``finish`` reports every problem.
    """

    def __init__(self, model: str) -> None:
        """Start encoding the vectors of `model`."""
        self._where = f"embeddings[{model!r}]"
        self._problems: list[str] = []
        self._lengths: set[int] = set()
        self._previous: str | None = None
        self._digest = hashlib.sha256()
        self._size = 0

    def encode(self, sha: str, vector: Sequence[float]) -> bytes | None:
        """The file line of the pair, or None once a problem has been found."""
        where = self._where
        self._lengths.add(len(vector))
        if not _SHA256_RE.match(sha):
            self._problems.append(f"{where}: {sha!r} is not a sha256 hex digest")
            return None
        previous = self._previous
        if previous == sha:
            self._problems.append(f"{where}: {sha!r} is a duplicate")
        elif previous is not None and sha < previous:
            self._problems.append(f"{where}: {sha!r} is not sorted after {previous!r}")
        self._previous = sha
        if self._problems:
            return None
        record = {
            "embedding_text_sha256": sha,
            "dims": len(vector),
            "vector": encode_vector(vector),
        }
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        self._digest.update(line)
        self._size += len(line)
        return line

    def finish(self) -> tuple[BundleFile, int]:
        """Size and digest of the encoded lines, and the vectors' dimension.

        Raises:
            BundleValidationError: a pair was invalid or the vectors differ in length.
        """
        lengths = self._lengths
        if len(lengths) != 1 or 0 in lengths:
            self._problems.append(
                f"{self._where}: vectors must share one non-zero length, "
                f"got {sorted(lengths)}"
            )
        if self._problems:
            raise BundleValidationError(self._problems)
        return BundleFile(sha256=self._digest.hexdigest(), bytes=self._size), next(
            iter(lengths)
        )


def with_embedding_file(
    manifest: BundleManifest, model: str, dims: int, listed: BundleFile
) -> BundleManifest:
    """`manifest` with the embedding file of `model` added or replaced."""
    name = embedding_file_name(model)
    embeddings = sorted(
        [
            *(entry for entry in manifest.embeddings if entry.model != model),
            BundleEmbeddingFile(model=model, dims=dims, file=name),
        ],
        key=lambda entry: entry.model,
    )
    files = {
        file: entry
        for file, entry in manifest.files.items()
        if not file.startswith(f"{EMBEDDINGS_DIR}/")
    }
    for entry in embeddings:
        current = listed if entry.model == model else manifest.files.get(entry.file)
        if current is not None:
            files[entry.file] = current
    return manifest.model_copy(update={"files": files, "embeddings": embeddings})


def digest_problems(
    name: str, size: int, sha256: str, expected: BundleFile
) -> list[str]:
    """Problems of a file of `size` bytes and `sha256` against the manifest's entry."""
    problems: list[str] = []
    if size != expected.bytes:
        problems.append(
            f"{name}: size {size} bytes does not match manifest ({expected.bytes})"
        )
    if sha256 != expected.sha256:
        problems.append(f"{name}: sha256 does not match manifest")
    return problems


def _format_loc(loc: Sequence[int | str]) -> str:
    text = ""
    for part in loc:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else part
    return text or "(root)"


def _validation_problems(where: str, error: ValidationError) -> list[str]:
    return [
        f"{where}: {_format_loc(detail['loc'])}: {detail['msg']}"
        for detail in error.errors()
    ]


def _embedding_entries(
    manifest: BundleManifest, problems: list[str]
) -> tuple[set[str], dict[str, int]]:
    """Check the manifest's embedding entries.

    Returns the expected embedding file names and the dims of each valid listed file.
    """
    expected_embedding_files: set[str] = set()
    embedding_dims: dict[str, int] = {}
    seen_models: set[str] = set()
    for index, entry in enumerate(manifest.embeddings):
        where = f"{MANIFEST_FILE}: embeddings[{index}]"
        expected_file = embedding_file_name(entry.model)
        if not model_slug(entry.model):
            problems.append(f"{where}.model: must contain letters or digits")
            continue
        if entry.model in seen_models:
            problems.append(f"{where}.model: duplicate model {entry.model!r}")
        seen_models.add(entry.model)
        if entry.dims < 1:
            problems.append(f"{where}.dims: must be >= 1, got {entry.dims}")
        if entry.file != expected_file:
            problems.append(
                f"{where}.file: expected {expected_file!r}, got {entry.file!r}"
            )
        elif entry.file not in manifest.files:
            problems.append(f"{where}.file: {entry.file!r} is not listed in files")
        elif entry.dims >= 1:
            embedding_dims.setdefault(entry.file, entry.dims)
        expected_embedding_files.add(expected_file)
    return expected_embedding_files, embedding_dims


def _vector_bytes(data: str, dims: int) -> bytes:
    try:
        raw = base64.b64decode(data, validate=True)
    except binascii.Error as error:
        raise ValueError(f"vector is not valid base64: {error}") from error
    if len(raw) != dims * 4:
        raise ValueError(f"vector has {len(raw)} bytes, expected {dims * 4} (dims * 4)")
    return raw


def _record_count(text: str) -> int:
    return sum(1 for line in text.split("\n") if line.strip())


def _parse_jsonl[RecordT: BaseModel](
    name: str, text: str, model: type[RecordT], problems: list[str]
) -> list[tuple[int, RecordT]]:
    records: list[tuple[int, RecordT]] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            records.append((line_number, model.model_validate_json(line)))
        except ValidationError as error:
            problems.extend(_validation_problems(f"{name}:{line_number}", error))
    return records


def _parse_json_list[RecordT](
    name: str,
    text: str | None,
    adapter: TypeAdapter[list[RecordT]],
    problems: list[str],
) -> list[RecordT]:
    if text is None:
        return []
    try:
        return adapter.validate_json(text)
    except ValidationError as error:
        problems.extend(_validation_problems(name, error))
        return []


def _page_problems(
    where: str, prefix: str, start_page: int | None, end_page: int | None
) -> list[str]:
    problems = [
        f"{where}: {prefix}{field}: must be >= 1, got {page}"
        for field, page in (("start_page", start_page), ("end_page", end_page))
        if page is not None and page < 1
    ]
    if start_page is not None and end_page is not None and start_page > end_page:
        problems.append(
            f"{where}: {prefix}start_page: {start_page} is after end_page {end_page}"
        )
    return problems


def _content_problems(
    documents: Sequence[tuple[int, DocumentRecord]],
    sections: Sequence[tuple[int, SectionRecord]],
    glossary: Sequence[GlossaryEntry],
    mappings: Sequence[ColloquialMappingRecord],
) -> list[str]:
    """Cross-record problems: duplicate or empty keys, unknown references, bad pages.

    Records are paired with their line number (or 1-based position) for messages.
    """
    problems: list[str] = []
    document_lines = _document_lines(documents, problems)
    section_lines = _section_lines(sections, document_lines, problems)
    _glossary_problems(glossary, problems)
    _mapping_problems(mappings, section_lines, problems)
    return problems


def _document_lines(
    documents: Sequence[tuple[int, DocumentRecord]], problems: list[str]
) -> dict[str, int]:
    """Check document keys and return the first line of each valid key."""
    document_lines: dict[str, int] = {}
    for line, document in documents:
        where = f"{DOCUMENTS_FILE}:{line}"
        if not document.key.strip():
            problems.append(f"{where}: key: must not be empty")
        elif document.key in document_lines:
            problems.append(
                f"{where}: key: duplicate document key {document.key!r} "
                f"(first on line {document_lines[document.key]})"
            )
        else:
            document_lines[document.key] = line
    return document_lines


def _section_lines(
    sections: Sequence[tuple[int, SectionRecord]],
    document_lines: dict[str, int],
    problems: list[str],
) -> dict[str, int]:
    """Check sections and return the first line of each valid section key."""
    section_lines: dict[str, int] = {}
    ordinal_lines: dict[tuple[str, int], int] = {}
    for line, section in sections:
        where = f"{SECTIONS_FILE}:{line}"
        if not section.key.strip():
            problems.append(f"{where}: key: must not be empty")
        elif section.key in section_lines:
            problems.append(
                f"{where}: key: duplicate section key {section.key!r} "
                f"(first on line {section_lines[section.key]})"
            )
        else:
            section_lines[section.key] = line
        if section.document_key not in document_lines:
            problems.append(
                f"{where}: document_key: unknown document {section.document_key!r}"
            )
        ordinal_key = (section.document_key, section.ordinal)
        if ordinal_key in ordinal_lines:
            problems.append(
                f"{where}: ordinal: duplicate ordinal {section.ordinal} in document "
                f"{section.document_key!r} (first on line {ordinal_lines[ordinal_key]})"
            )
        else:
            ordinal_lines[ordinal_key] = line
        problems.extend(_page_problems(where, "", section.start_page, section.end_page))
        problems.extend(_block_problems(where, section.blocks))
    return section_lines


def _block_problems(where: str, blocks: Sequence[BlockRecord]) -> list[str]:
    """Problems of one section's blocks: none at all, empty markdown, bad pages."""
    problems: list[str] = []
    if not blocks:
        problems.append(f"{where}: blocks: must contain at least one block")
    for index, block in enumerate(blocks):
        prefix = f"blocks[{index}]."
        if not block.markdown.strip():
            problems.append(f"{where}: {prefix}markdown: must not be empty")
        problems.extend(_page_problems(where, prefix, block.start_page, block.end_page))
    return problems


def _glossary_problems(glossary: Sequence[GlossaryEntry], problems: list[str]) -> None:
    """Report empty terms and terms repeated case-insensitively."""
    term_indexes: dict[str, int] = {}
    for index, entry in enumerate(glossary):
        where = f"{GLOSSARY_FILE}: [{index}].term"
        term = entry.term.strip()
        if not term:
            problems.append(f"{where}: must not be empty")
        elif term.casefold() in term_indexes:
            problems.append(
                f"{where}: duplicate term {term!r} (case-insensitive, first at "
                f"[{term_indexes[term.casefold()]}])"
            )
        else:
            term_indexes[term.casefold()] = index


def _mapping_problems(
    mappings: Sequence[ColloquialMappingRecord],
    section_lines: dict[str, int],
    problems: list[str],
) -> None:
    """Report mapped sections that are unknown or already mapped by another record."""
    mapped_by: dict[str, int] = {}
    for index, record in enumerate(mappings):
        for key_index, section_key in enumerate(record.section_keys):
            where = f"{COLLOQUIAL_MAPPINGS_FILE}: [{index}].section_keys[{key_index}]"
            if section_key not in section_lines:
                problems.append(f"{where}: unknown section {section_key!r}")
            elif section_key in mapped_by:
                problems.append(
                    f"{where}: section {section_key!r} is already mapped by "
                    f"[{mapped_by[section_key]}]"
                )
            else:
                mapped_by[section_key] = index


def _jsonl_bytes(records: Sequence[BaseModel]) -> bytes:
    return "".join(f"{record.model_dump_json()}\n" for record in records).encode()


def _json_list_bytes(records: Sequence[BaseModel]) -> bytes:
    return (
        json.dumps(
            [record.model_dump(mode="json") for record in records],
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode()
