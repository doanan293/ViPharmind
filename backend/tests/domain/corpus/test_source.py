import uuid
from datetime import UTC, datetime

from pharma_agent.domain.corpus.source import (
    MAX_DOCUMENT_CHARS,
    IngestJob,
    JobStatus,
    JobStep,
    document_problem,
)

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def test_documents_need_a_title_and_bounded_text() -> None:
    assert document_problem("Paracetamol", "Nội dung") is None
    assert document_problem("  ", "x") == "the title is required"
    assert document_problem("x" * 201, "x") == "the title is too long"
    assert document_problem("t", "   ") == "the document is empty"
    too_long = "x" * (MAX_DOCUMENT_CHARS + 1)
    assert document_problem("t", too_long) == (
        f"the document has more than {MAX_DOCUMENT_CHARS} characters"
    )


def test_only_queued_and_running_jobs_are_open() -> None:
    def job(status: JobStatus) -> IngestJob:
        return IngestJob(
            id=uuid.uuid4(),
            collection_id=uuid.uuid4(),
            release_id=None,
            status=status,
            step=JobStep.BUNDLE,
            progress=0,
            error=None,
            requested_by=None,
            attempts=0,
            created_at=NOW,
            started_at=None,
            finished_at=None,
        )

    assert [job(s).is_open for s in JobStatus] == [True, True, False, False]
