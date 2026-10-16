from pydantic import BaseModel, Field

from pharma_agent.domain.agent.react import Shown
from pharma_agent.domain.agent.run import AgentRun
from pharma_agent.domain.conversation.models import Citation
from pharma_agent.domain.llm.models import ChatMessage, ToolCall
from pharma_agent.domain.retrieval.models import Query


class ReactLoop(BaseModel):
    """The ReAct agent's working state within one turn (spec v2 §2.4)."""

    messages: list[ChatMessage] = Field(default_factory=list)
    pending_calls: list[ToolCall] = Field(default_factory=list)
    shown: Shown = Field(default_factory=Shown)
    final_text: str = ""
    answered: bool = False
    # The next agent call answers without tools.
    forced: bool = False


class ChatTurnState(BaseModel):
    run: AgentRun
    pending_queries: list[Query] = Field(default_factory=list)
    last_gaps: list[str] = Field(default_factory=list)
    answer_text: str = ""
    # The numbered evidence the answer prompt carried.
    context_text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    # Set only by the ReAct graph.
    react: ReactLoop | None = None
