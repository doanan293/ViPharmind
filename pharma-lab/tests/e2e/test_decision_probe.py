import asyncio

import pytest
from pharma_agent.domain.llm.decision import Decision

from pharma_lab.e2e.decision_probe import (
    ProbeResult,
    probe_state,
    recommended_evidence_chars,
    run_probe,
)


def test_probe_state_holds_exactly_the_requested_characters() -> None:
    state = probe_state(["a" * 100, "b" * 100, "c" * 100], chars=250)
    evidence = state["evidence"]
    assert isinstance(evidence, list)
    texts = [item["text"] for item in evidence]
    assert sum(len(t) for t in texts) == 250
    assert texts[-1] == "c" * 50


def test_probe_state_rejects_chunks_that_are_too_short() -> None:
    with pytest.raises(ValueError, match="fewer than"):
        probe_state(["a" * 10], chars=250)


def test_run_probe_reports_chars_per_token() -> None:
    class Port:
        async def decide(self, role, state, questions):
            return Decision(
                answers={"warmup": 0.5},
                model="jev-1.13.0",
                input_tokens=20_000,
                seconds=0.9,
                raw={},
            )

    result = asyncio.run(run_probe(Port(), probe_state(["x" * 60_000], chars=60_000)))
    assert result.input_tokens == 20_000 and result.chars_per_token == pytest.approx(
        3.0
    )
    assert recommended_evidence_chars(result) == 60_000
    assert (
        recommended_evidence_chars(ProbeResult(30_000, 60_000, 2.0, 1.0, "jev-1.13.0"))
        == 48_000
    )


def test_recommendation_scales_the_probed_characters_not_the_default() -> None:
    # 30k characters probed at --chars 30000 took 30k tokens: 24k tokens hold 24k chars.
    probed = ProbeResult(30_000, 30_000, 1.0, 1.0, "jev-1.13.0")
    assert recommended_evidence_chars(probed) == 24_000
    # Under the ceiling the budget is never raised above the current one.
    light = ProbeResult(10_000, 30_000, 3.0, 1.0, "jev-1.13.0")
    assert recommended_evidence_chars(light) == 60_000
