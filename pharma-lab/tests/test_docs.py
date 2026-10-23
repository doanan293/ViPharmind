import re
import shlex

import pytest
from typer.testing import CliRunner

from pharma_lab.cli.app import app
from pharma_lab.config.paths import PROJECT_ROOT

GUIDES = PROJECT_ROOT / "docs" / "guides"
DOCS = (PROJECT_ROOT / "README.md", *sorted(GUIDES.glob("*.md")))


def _code_lines(text: str) -> list[str]:
    lines: list[str] = []
    inside = False
    pending = ""
    for raw in text.splitlines():
        if raw.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            continue
        if raw.rstrip().endswith("\\"):
            pending += raw.rstrip()[:-1] + " "
            continue
        lines.append((pending + raw).strip())
        pending = ""
    return lines


def _seed_commands() -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    for doc in DOCS:
        for line in _code_lines(doc.read_text(encoding="utf-8")):
            if line.startswith("uv run pharma-lab "):
                commands.append((doc.name, shlex.split(line, comments=True)[3:]))
    return commands


@pytest.mark.parametrize(("doc", "args"), _seed_commands())
def test_documented_seed_commands_parse(doc: str, args: list[str]) -> None:
    result = CliRunner().invoke(app, [*args, "--help"])

    assert result.exit_code == 0, (doc, args, result.output)


def _guide(name: str) -> str:
    return (GUIDES / name).read_text(encoding="utf-8")


def test_guides_do_not_mention_removed_serve_commands() -> None:
    removed = re.compile(
        r"llm-server|rerank-server|embed-server|cloudflared|trycloudflare", re.I
    )

    found = [
        f"{doc.name}:{number}"
        for doc in DOCS
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1)
        if removed.search(line)
    ]

    assert found == []


def test_guides_do_not_describe_the_old_single_job_run() -> None:
    stale = (
        "Một lệnh là một job",
        "thì lệnh từ chối",
        "chưa nhận `--pipeline-option`",
        "không chạy được trong kernel",
        "Kaggle không được dùng để phục vụ model ra ngoài (một account đã bị khóa",
    )

    found = [
        f"{doc.name}: {phrase}"
        for doc in DOCS
        for phrase in stale
        if phrase in doc.read_text(encoding="utf-8")
    ]

    assert found == []


@pytest.mark.parametrize(
    ("guide", "needles"),
    [
        (
            "e2e-evaluation.md",
            (
                "e2e status",
                "--drain",
                "--parallel",
                "--with-proxy-credentials",
                "--latency",
                "--judge",
                "--retry-stuck",
                "kaggle status",
            ),
        ),
        ("workflow-local-kaggle.md", ("kaggle status", "--parallel", "--drain")),
        (
            "cli-reference.md",
            ("e2e status", "kaggle status", "--parallel", "--drain", "--llm"),
        ),
    ],
)
def test_guides_document_the_resumable_kaggle_workflow(
    guide: str, needles: tuple[str, ...]
) -> None:
    text = _guide(guide)

    assert [needle for needle in needles if needle not in text] == []
