"""The retrieval benchmark's generated groups (spec v2 §3.1, §4.D).

The 10,000 rule-built questions keep their six groups. Three more groups are generated
from the corpus and from those questions, and appended to the same file so that every
table reports the same groups: `colloquial` (a product named only by an alias absent from
its leaflet), `glossary` (a plain-language phrase for a term the formulary writes only
abbreviated) and `conversational` (a follow-up turn that inherits a benchmark question's
gold sections).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pharma_lab.e2e.conversational import build_conversational
from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden_generate import (
    benchmark_row,
    colloquial_benchmark,
    glossary_benchmark,
)

GENERATED_GROUPS = ("colloquial", "glossary", "conversational")


def extend_rows(
    base: Sequence[dict],
    corpus: CorpusText,
    aliases: Sequence[tuple[str, Sequence[str]]],
    *,
    covered: Mapping[str, bool] | None,
    conversational_total: int,
    seed: int,
) -> list[dict]:
    """The base rows without any generated group, then the colloquial, glossary and
    conversational rows, so extending an extended file gives the same file."""
    rows = [row for row in base if row.get("eval_group") not in GENERATED_GROUPS]
    probes = [*colloquial_benchmark(corpus, aliases), *glossary_benchmark(corpus)]
    conversational = build_conversational(
        rows, corpus, total=conversational_total, seed=seed, covered=covered
    )
    return [*rows, *(benchmark_row(probe) for probe in probes), *conversational]
