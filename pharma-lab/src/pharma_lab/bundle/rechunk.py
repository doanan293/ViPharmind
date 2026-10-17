"""Copy a knowledge bundle under another collection with another chunking: one chunk
per section (D7) or no chunk enrichment (D2)."""

from dataclasses import dataclass
from pathlib import Path

from pharma_agent.domain.corpus.bundle import (
    MAX_CHUNK_CHARS,
    TARGET_CHUNK_CHARS,
    BundleChunking,
    BundleCollection,
    BundleManifest,
    read_bundle,
)

from pharma_lab.bundle.io import write_validated_bundle


@dataclass(frozen=True)
class RechunkRequest:
    bundle_dir: Path
    output_dir: Path
    collection_key: str
    collection_title: str
    target_chars: int = TARGET_CHUNK_CHARS
    max_chars: int = MAX_CHUNK_CHARS
    enrichment: bool = True


def rechunk_bundle(request: RechunkRequest) -> BundleManifest:
    """Write the bundle's content with a new collection and chunking, and no vectors.

    The vectors of the source belong to its chunks; `bundle embed` embeds the new ones
    and reuses the text-embedding cache for every chunk text both bundles share.
    """
    if Path(request.output_dir).resolve() == Path(request.bundle_dir).resolve():
        raise ValueError("rechunk output must differ from the source bundle")
    source = read_bundle(request.bundle_dir)
    manifest = source.manifest.model_copy(
        update={
            "collection": BundleCollection(
                key=request.collection_key, title=request.collection_title
            ),
            "chunking": BundleChunking(
                target_chars=request.target_chars,
                max_chars=request.max_chars,
                enrichment=request.enrichment,
            ),
            "files": {},
            "embeddings": [],
        }
    )
    return write_validated_bundle(
        source.model_copy(update={"manifest": manifest}), request.output_dir
    )
