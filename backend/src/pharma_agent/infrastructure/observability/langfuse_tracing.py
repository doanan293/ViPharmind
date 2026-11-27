"""Langfuse tracing: one trace per chat turn.

The trace has a deterministic id derived from run_id, LangGraph node spans nested inside
it, and user feedback recorded as a score on it.
"""

import logging
from collections.abc import Generator, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse, propagate_attributes
from langfuse._client.span import LangfuseAgent
from langfuse.langchain import CallbackHandler

from pharma_agent.application.tracing import TraceHandle
from pharma_agent.domain.agent.run import AgentRun
from pharma_agent.infrastructure.settings import LangfuseSettings

logger = logging.getLogger(__name__)
FEEDBACK_SCORE_NAME = "user_feedback"
TURN_OBSERVATION_NAME = "chat_turn"


class _Handle:
    def __init__(self, span: LangfuseAgent, handler: CallbackHandler) -> None:
        self._span = span
        self._callbacks: tuple[BaseCallbackHandler, ...] = (handler,)

    @property
    def callbacks(self) -> Sequence[BaseCallbackHandler]:
        return self._callbacks

    def finish(self, *, status: str, output: str) -> None:
        self._span.update(output=output, metadata={"status": status})


class LangfuseTracing:
    """Tracing over Langfuse: one trace per chat turn and feedback as its score."""

    def __init__(self, client: Langfuse, *, public_key: str) -> None:
        """Trace through `client`, whose `public_key` the LangChain handler needs."""
        # Langfuse integrations resolve their client by public key; without it they give up
        # (and silently skip tracing) as soon as a process holds more than one client.
        self._client = client
        self._public_key = public_key

    @classmethod
    def from_settings(cls, settings: LangfuseSettings) -> "LangfuseTracing":
        """Build a Langfuse client from settings.

        Raises:
            ValueError: When PHARMA_LANGFUSE__PUBLIC_KEY is not set.
        """
        if not settings.public_key:
            raise ValueError("set PHARMA_LANGFUSE__PUBLIC_KEY to enable Langfuse")
        return cls(
            Langfuse(
                public_key=settings.public_key,
                secret_key=settings.secret_key,
                base_url=settings.host,
            ),
            public_key=settings.public_key,
        )

    def trace_id_for(self, run_id: str) -> str:
        """The Langfuse trace id of a run, derived deterministically from `run_id`."""
        return self._client.create_trace_id(seed=run_id)

    @contextmanager
    def _trace(self, run: AgentRun) -> Generator[TraceHandle]:
        with ExitStack() as stack:
            stack.enter_context(
                propagate_attributes(
                    user_id=run.user_id,
                    session_id=run.conversation_id,
                    trace_name=TURN_OBSERVATION_NAME,
                    metadata={"run_id": run.run_id},
                )
            )
            span = stack.enter_context(
                self._client.start_as_current_observation(
                    trace_context={"trace_id": self.trace_id_for(run.run_id)},
                    name=TURN_OBSERVATION_NAME,
                    as_type="agent",
                    input={"query": run.original_query},
                )
            )
            yield _Handle(span, CallbackHandler(public_key=self._public_key))

    def trace_turn(self, run: AgentRun) -> AbstractContextManager[TraceHandle]:
        """Open the turn's trace and `agent` span; the handle has the callbacks."""
        return self._trace(run)

    def record_feedback(self, *, run_id: str, rating: str, note: str) -> None:
        """Score the run's trace 1.0 for `up`, else 0.0, with `note` as comment."""
        self._client.create_score(
            name=FEEDBACK_SCORE_NAME,
            value=1.0 if rating == "up" else 0.0,
            trace_id=self.trace_id_for(run_id),
            comment=note or None,
            data_type="NUMERIC",
        )

    def flush(self) -> None:
        """Send buffered events to Langfuse."""
        self._client.flush()

    def shutdown(self) -> None:
        """Flush and stop the client; a failure is logged, not raised."""
        try:
            self._client.shutdown()
        except Exception:
            logger.exception("langfuse shutdown failed")
