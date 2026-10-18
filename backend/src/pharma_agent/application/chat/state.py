from pydantic import BaseModel, Field

from pharma_agent.domain.agent.react import Shown
from pharma_agent.domain.agent.run import AgentRun
from pharma_agent.domain.conversation.models import Citation
from pharma_agent.domain.retrieval.models import Query


class ReactAnswer(BaseModel):
    """What the ReAct agent hands to finalize (spec v2 §2.4): the chunks it was shown
    and its final answer text."""

    shown: Shown = Field(default_factory=Shown)
    final_text: str = ""


class ChatTurnState(BaseModel):
    run: AgentRun
    pending_queries: list[Query] = Field(default_factory=list)
    last_gaps: list[str] = Field(default_factory=list)
    answer_text: str = ""
    # The numbered evidence the answer prompt carried.
    context_text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    # Set only by the ReAct graph.
    react: ReactAnswer | None = None
