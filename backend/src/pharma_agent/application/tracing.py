"""Ports for observability: one trace per chat turn, and scores attached to a turn later."""

from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext
from typing import Protocol, override

from langchain_core.callbacks import BaseCallbackHandler

from pharma_agent.domain.agent.run import AgentRun


class TraceHandle(Protocol):
    """The trace of one chat turn, open while the turn runs."""

    @property
    def callbacks(self) -> Sequence[BaseCallbackHandler]:
        """LangChain callbacks to attach to the graph run so node spans join the trace."""
        ...

    def finish(self, *, status: str, output: str) -> None:
        """Close the trace with the turn's final status and answer text."""
        ...


class TurnTracer(Protocol):
    """Opens one trace per chat turn."""

    def trace_turn(self, run: AgentRun) -> AbstractContextManager[TraceHandle]:
        """Return a context manager that opens the trace of `run` and closes it on exit."""
        ...


class ScoreSink(Protocol):
    """Receives user scores for traced turns."""

    def record_feedback(self, *, run_id: str, rating: str, note: str) -> None:
        """Attach a user rating to the trace of the turn identified by run_id."""
        ...


class Tracing(TurnTracer, ScoreSink, Protocol):
    """A tracer that can also score its own traces (Langfuse, or the null implementation)."""


class _NullHandle(TraceHandle):
    @property
    @override
    def callbacks(self) -> Sequence[BaseCallbackHandler]:
        """No callbacks: nothing is traced."""
        return ()

    @override
    def finish(self, *, status: str, output: str) -> None:
        """Record nothing."""


class NullTracing(Tracing):
    """Used when Langfuse is not configured."""

    @override
    def trace_turn(self, run: AgentRun) -> AbstractContextManager[TraceHandle]:
        """Return a handle that records nothing."""
        return nullcontext(_NullHandle())

    @override
    def record_feedback(self, *, run_id: str, rating: str, note: str) -> None:
        """Ignore the rating."""
