import hashlib
import unicodedata
import uuid

from pharma_agent.domain.corpus.bundle import BlockKind, BlockRecord
from pharma_agent.domain.corpus.identity import (
    CORPUS_NAMESPACE,
    canonical_json,
    chunk_version_id,
    sha256_hex,
)

BLOCKS = [
    BlockRecord(
        kind=BlockKind.PROSE,
        markdown="Người lớn: uống 500 mg - 1 g mỗi 4 - 6 giờ, tối đa 4 g/ngày.",
        start_page=1203,
        end_page=1203,
    ),
    BlockRecord(
        kind=BlockKind.TABLE,
        markdown="| Tuổi | Liều |\n| --- | --- |\n| Trẻ em | 10 - 15 mg/kg |",
        start_page=1204,
        end_page=1204,
        table_key="tbl-0007",
    ),
]
CHUNK_TEXT = "Người lớn: uống 500 mg - 1 g mỗi 4 - 6 giờ, tối đa 4 g/ngày."
EMBEDDING_TEXT = f"PARACETAMOL\n> Liều lượng và cách dùng\n\n{CHUNK_TEXT}"


def test_namespace_is_pinned() -> None:
    assert uuid.uuid5(uuid.NAMESPACE_URL, "pharma-agent:corpus:v1") == CORPUS_NAMESPACE


def test_canonical_json_sorts_keys_compacts_and_normalizes_strings() -> None:
    value = {
        "b": [unicodedata.normalize("NFD", "Liều") + "  \r\n", 2.5],
        "a": {"z": 1, "y": None},
    }

    assert canonical_json(value) == '{"a":{"y":null,"z":1},"b":["Liều",2.5]}'


def test_sha256_hex_hashes_utf8_text() -> None:
    assert sha256_hex("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert sha256_hex("Liều") == hashlib.sha256("Liều".encode()).hexdigest()


DOCUMENT_ID = uuid.uuid5(CORPUS_NAMESPACE, "document\x1ftest")
SECTION_KEYS = ["drug:paracetamol:lieu-dung"]


def _id(**changes: object) -> uuid.UUID:
    args: dict = {
        "document_id": DOCUMENT_ID,
        "section_keys": SECTION_KEYS,
        "chunk_text": CHUNK_TEXT,
        "embedding_text": EMBEDDING_TEXT,
        "chunker_version": "chunker-v1",
    } | changes
    return chunk_version_id(**args)


def test_chunk_version_id_follows_the_spec_formula() -> None:
    digest = sha256_hex(
        "\x1f".join(
            (
                str(DOCUMENT_ID),
                ",".join(SECTION_KEYS),
                CHUNK_TEXT,
                EMBEDDING_TEXT,
                "chunker-v1",
            )
        )
    )

    assert _id() == uuid.uuid5(CORPUS_NAMESPACE, "chunk\x1f" + digest)


def test_chunk_version_id_changes_with_every_input_but_not_with_whitespace() -> None:
    base = _id()
    enriched = (
        f"{EMBEDDING_TEXT}\n\nThuật ngữ: G6PD = glucose-6-phosphate dehydrogenase"
    )

    assert _id(chunker_version="chunker-v2") != base
    assert _id(embedding_text=enriched) != base
    assert _id(chunk_text=f"{CHUNK_TEXT} Trẻ em") != base
    assert _id(document_id=uuid.uuid5(CORPUS_NAMESPACE, "document\x1fother")) != base
    assert _id(section_keys=["drug:paracetamol:lieu-dung-2"]) != base
    assert (
        _id(
            chunk_text=f"{CHUNK_TEXT}  \n",
            embedding_text=EMBEDDING_TEXT.replace("\n", "\r\n"),
        )
        == base
    )
