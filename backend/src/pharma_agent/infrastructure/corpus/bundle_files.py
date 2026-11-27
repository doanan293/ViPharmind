"""Knowledge bundle files on disk: reading, writing and locking a bundle directory.

Public API: pharma-lab builds a ``KnowledgeBundle``, calls ``write_bundle`` and then adds
each model's vectors with ``write_bundle_embeddings``; the backend import calls
``read_bundle`` and loads the vectors of its model with ``read_bundle_embeddings``. The
format and its checks live in ``pharma_agent.domain.corpus.bundle``; this module only moves
bytes. Embedding files are streamed line by line, so memory holds at most one model's
vectors however many models a bundle ships.
"""

import fcntl
import os
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path

from pharma_agent.domain.corpus.bundle import (
    EMBEDDINGS_DIR,
    MANIFEST_FILE,
    BundleFile,
    BundleManifest,
    BundleValidationError,
    EmbeddingFileCheck,
    EmbeddingLineEncoder,
    KnowledgeBundle,
    assemble_bundle,
    content_text,
    declared_embedding_file,
    embedding_target,
    encode_bundle,
    listed_files,
    manifest_json,
    missing_file_problem,
    model_slug,
    parse_manifest,
    with_embedding_file,
)


def read_bundle(directory: Path) -> KnowledgeBundle:
    """Read and validate a bundle directory; every problem is reported at once.

    Embedding files are checked line by line without keeping their vectors.

    Raises:
        BundleValidationError: the bundle is invalid, listing every problem.
    """
    manifest = _read_manifest(directory)
    problems: list[str] = []
    line_problems: list[str] = []
    texts = _read_manifest_files(directory, manifest, problems, line_problems)
    return assemble_bundle(manifest, texts, problems, line_problems)


def read_bundle_embeddings(
    directory: Path, manifest: BundleManifest, model: str, dims: int
) -> dict[str, list[float]]:
    """Vectors of `model` keyed by embedding_text_sha256, streamed from its file.

    Empty when `manifest` declares no embeddings for `model` with `dims`. The file is
    checked again, so a change after ``read_bundle`` raises BundleValidationError.

    Raises:
        BundleValidationError: the embedding file is missing or invalid.
    """
    declared = declared_embedding_file(manifest, model, dims)
    if declared is None:
        return {}
    name, expected = declared
    path = directory / name
    if not path.is_file():
        raise BundleValidationError([missing_file_problem(name)])

    vectors: dict[str, list[float]] = {}

    def keep(sha: str, vector: list[float]) -> None:
        vectors[sha] = vector

    problems: list[str] = []
    check = EmbeddingFileCheck(name, dims, problems, keep)
    _scan_lines(path, check)
    problems.extend(check.digest_problems(expected))
    if problems:
        raise BundleValidationError(problems)
    return vectors


def write_bundle(bundle: KnowledgeBundle, directory: Path) -> BundleManifest:
    """Validate, write the content files and return the manifest with computed digests.

    The manifest lists no embeddings; add them with ``write_bundle_embeddings``.

    Raises:
        BundleValidationError: the content is invalid; nothing is written.
    """
    manifest, payloads = encode_bundle(bundle)
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (directory / name).write_bytes(data)
    _write_manifest(directory, manifest)
    return manifest


def write_bundle_embeddings(
    directory: Path, model: str, vectors: Iterable[tuple[str, Sequence[float]]]
) -> BundleManifest:
    """Add or replace the embedding file of `model` and return the updated manifest.

    `vectors` yields (embedding_text_sha256, vector) pairs sorted by hash without
    duplicates. They are streamed to a temporary file that replaces the model's file only
    when every pair is valid; the manifest is replaced last. Other models' files are not
    read, so memory does not grow with the number or size of the models.

    Raises:
        BundleValidationError: the manifest, the model name or a pair is invalid.
    """
    # Runs that embed different models into one bundle may finish together; each must
    # read the manifest the other has just written, or one entry is lost.
    with _manifest_lock(directory):
        manifest = _read_manifest(directory)
        name = embedding_target(manifest, model)
        temporary = directory / f".{model_slug(model)}.jsonl.tmp"
        try:
            listed, dims = _write_embedding_lines(temporary, model, vectors)
            (directory / EMBEDDINGS_DIR).mkdir(exist_ok=True)
            temporary.replace(directory / name)
        finally:
            temporary.unlink(missing_ok=True)
        updated = with_embedding_file(manifest, model, dims, listed)
        _write_manifest(directory, updated)
        return updated


@contextmanager
def _manifest_lock(directory: Path) -> Generator[None]:
    """Serialise read-modify-write of a bundle's manifest across processes."""
    # The lock is held on the directory itself, so the bundle gains no extra file.
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _read_manifest(directory: Path) -> BundleManifest:
    manifest_path = directory / MANIFEST_FILE
    if not manifest_path.is_file():
        raise BundleValidationError([missing_file_problem(MANIFEST_FILE)])
    return parse_manifest(manifest_path.read_bytes())


def _write_manifest(directory: Path, manifest: BundleManifest) -> None:
    """Replace the manifest atomically so a reader never sees a partial file."""
    temporary = directory / f".{MANIFEST_FILE}.tmp"
    temporary.write_text(manifest_json(manifest), encoding="utf-8")
    temporary.replace(directory / MANIFEST_FILE)


def _write_embedding_lines(
    path: Path, model: str, vectors: Iterable[tuple[str, Sequence[float]]]
) -> tuple[BundleFile, int]:
    encoder = EmbeddingLineEncoder(model)
    with path.open("wb") as handle:
        for sha, vector in vectors:
            line = encoder.encode(sha, vector)
            if line is not None:
                handle.write(line)
    return encoder.finish()


def _read_manifest_files(
    directory: Path,
    manifest: BundleManifest,
    problems: list[str],
    line_problems: list[str],
) -> dict[str, str]:
    """Check every listed file and return the text of the content files.

    Digest problems follow the manifest's file order in `problems`; embedding files are
    streamed and their line problems go to `line_problems`.
    """
    texts: dict[str, str] = {}
    for listed in listed_files(manifest, problems):
        if listed.problem is not None:
            problems.append(listed.problem)
            continue
        path = directory / listed.name
        if not path.is_file():
            problems.append(missing_file_problem(listed.name))
            continue
        if not listed.content:
            check = EmbeddingFileCheck(listed.name, listed.dims, line_problems)
            _scan_lines(path, check)
            problems.extend(check.digest_problems(listed.expected))
            continue
        text = content_text(listed.name, path.read_bytes(), listed.expected, problems)
        if text is not None:
            texts[listed.name] = text
    return texts


def _scan_lines(path: Path, check: EmbeddingFileCheck) -> None:
    """Stream the lines of the file at `path` into `check`."""
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            check.add(line_number, raw)
