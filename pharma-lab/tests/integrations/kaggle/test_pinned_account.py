from pathlib import Path

import pytest

from pharma_lab.config import paths
from pharma_lab.embeddings.service import KaggleTextEmbeddingBackend
from pharma_lab.evaluation.query_embedding_service import (
    KaggleQueryEmbeddingBackend,
    QueryEmbeddingRequest,
)
from pharma_lab.integrations.kaggle.job_lock import (
    KaggleAccountBusy,
    hold_pinned_account,
    kaggle_account_lock,
)


@pytest.fixture(autouse=True)
def _locks_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "LOCK_DIR", tmp_path / "locks")


def _busy(profile: str) -> bool:
    try:
        with kaggle_account_lock(profile):
            return False
    except KaggleAccountBusy:
        return True


@pytest.mark.parametrize("account", [None, "auto", "AUTO"])
def test_a_command_not_pinned_to_an_account_takes_no_account_lock(account) -> None:
    with hold_pinned_account(account):
        assert not _busy("acc1")


def test_a_pinned_command_holds_its_account() -> None:
    with hold_pinned_account(" acc2 "):
        assert _busy("acc2") and not _busy("acc1")
    assert not _busy("acc2")


def test_corpus_embedding_on_kaggle_holds_its_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bool] = []
    monkeypatch.setattr(
        KaggleTextEmbeddingBackend,
        "_run_unlocked",
        staticmethod(lambda request: seen.append(_busy("acc3"))),
    )
    request = type(
        "Request",
        (),
        {"cache_path": tmp_path / "cache.jsonl", "kaggle_account": "acc3"},
    )()

    KaggleTextEmbeddingBackend().run(request)

    assert seen == [True]


def test_query_embedding_on_kaggle_holds_its_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bool] = []
    monkeypatch.setattr(
        KaggleQueryEmbeddingBackend,
        "_run_kaggle_unlocked",
        staticmethod(lambda request: seen.append(_busy("acc1"))),
    )
    request = QueryEmbeddingRequest.__new__(QueryEmbeddingRequest)
    object.__setattr__(request, "output_dir", tmp_path / "queries")
    object.__setattr__(request, "kaggle_account", "acc1")

    KaggleQueryEmbeddingBackend._run_kaggle_orchestrator(request)

    assert seen == [True]
