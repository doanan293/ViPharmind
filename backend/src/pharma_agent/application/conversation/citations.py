"""Full text behind a citation (spec A §5.2); REST models keep snake_case."""

from pydantic import BaseModel

from pharma_agent.domain.conversation.models import CitationBlock


class CitationDetail(BaseModel):
    index: int
    source: str
    document_title: str
    section: str
    start_page: int | None
    end_page: int | None
    is_current: bool
    text: str

    @classmethod
    def of(cls, block: CitationBlock) -> "CitationDetail":
        citation = block.citation
        return cls(
            index=citation.index,
            source=citation.source,
            document_title=citation.title,
            section=citation.section,
            start_page=citation.start_page,
            end_page=citation.end_page,
            is_current=block.is_current,
            text=block.text,
        )
