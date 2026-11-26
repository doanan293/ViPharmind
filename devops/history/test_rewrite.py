import os
import subprocess
from pathlib import Path

import pytest
from rewrite import group_by_scope, main, rewrite, segments

ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**ENV, **(env or {})},
    )
    return out.stdout.strip()


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.clock = 1_700_000_000
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        git(path, "config", "user.name", "Dev")
        git(path, "config", "user.email", "dev@example.com")

    def _env(self) -> dict[str, str]:
        self.clock += 60
        date = f"{self.clock} +0700"
        return {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}

    def commit(self, message: str, files: dict[str, str | None]) -> str:
        for name, content in files.items():
            path = self.path / name
            if content is None:
                git(self.path, "rm", "-q", name)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            git(self.path, "add", name)
        git(self.path, "commit", "-q", "--allow-empty", "-m", message, env=self._env())
        return git(self.path, "rev-parse", "HEAD")

    def merge(self, branch: str, message: str) -> str:
        git(self.path, "merge", "-q", "--no-ff", "-m", message, branch, env=self._env())
        return git(self.path, "rev-parse", "HEAD")

    def tree(self, ref: str) -> str:
        return git(self.path, "rev-parse", f"{ref}^{{tree}}")


def build(repo: Repo, chat_touches_report: bool = False) -> None:
    """c0, then feat(chat) x2, docs(report), feat(chat), feat(auth) x2 on main;
    `tail` adds two clean-up commits on top of main."""
    repo.commit("chore: initial", {"README.md": "hello\n"})
    git(repo.path, "tag", "c0")
    repo.commit("feat(chat): stream answers", {"backend/chat/a.py": "a\n"})
    repo.commit("feat(chat): cite sources", {"backend/chat/b.py": "b\n"})
    repo.commit("docs(report): results table", {"docs/report/x.tex": "x\n"})
    chat = {"frontend/chat/c.tsx": "c\n"}
    if chat_touches_report:
        chat |= {"backend/chat/d.py": "d\n", "docs/report/x.tex": "x2\n"}
    repo.commit("feat(chat): chat page", chat)
    repo.commit("feat(auth): otp login", {"backend/auth/d.py": "d\n"})
    repo.commit("feat(auth): logout", {"backend/auth/e.py": "e\n"})
    git(repo.path, "checkout", "-q", "-b", "tail")
    repo.commit("fix(chat): empty answer", {"backend/chat/a.py": "a2\n"})
    repo.commit(
        "chore: drop report\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
        {"docs/report/x.tex": None},
    )
    git(repo.path, "checkout", "-q", "main")


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Repo:
    repo = Repo(tmp_path / "repo")
    build(repo)
    return repo


@pytest.fixture
def conflict_repo(tmp_path: Path) -> Repo:
    repo = Repo(tmp_path / "conflict")
    build(repo, chat_touches_report=True)
    return repo


def shape(segs) -> list[tuple[str, str, int]]:
    return [(s.kind, s.scope, s.n) for s in segs]


def test_segments_group_consecutive_scope(tmp_repo: Repo) -> None:
    assert shape(segments(tmp_repo.path, "c0", "main")) == [
        ("app", "chat", 2),
        ("research", "report", 1),
        ("app", "chat", 1),
        ("app", "auth", 2),
    ]


def test_scope_falls_back_to_most_changed_second_level_dir(tmp_repo: Repo) -> None:
    tmp_repo.commit(
        "add lab data",
        {
            "pharma-lab/data/x": "1\n",
            "pharma-lab/data/y": "2\n",
            "pharma-lab/src/z.py": "3\n",
        },
    )
    assert shape(segments(tmp_repo.path, "c0", "main"))[-1] == ("research", "data", 1)


def test_rewrite_keeps_trees_and_tail(tmp_repo: Repo) -> None:
    shas = rewrite(tmp_repo.path, "c0", "main", "main", "tail", "new")
    assert tmp_repo.tree("new") == tmp_repo.tree("tail")
    ends = [s.end for s in segments(tmp_repo.path, "c0", "main")]
    assert [tmp_repo.tree(s) for s in shas[:4]] == [tmp_repo.tree(e) for e in ends]
    assert len(shas) == 6
    assert git(tmp_repo.path, "rev-parse", "new") == shas[-1]


def test_rewrite_messages_and_identity(tmp_repo: Repo) -> None:
    shas = rewrite(tmp_repo.path, "c0", "main", "main", "tail", "new")
    first = git(tmp_repo.path, "log", "-1", "--format=%B", shas[0])
    assert first.splitlines()[0] == "feat(chat): stream answers"
    assert "- feat(chat): stream answers\n- feat(chat): cite sources" in first
    report = git(tmp_repo.path, "log", "-1", "--format=%s", shas[1])
    assert report == "docs(report): results table"
    ends = [s.end for s in segments(tmp_repo.path, "c0", "main")]
    fmt = "--format=%an %ae %ad %cn %ce %cd"
    assert git(tmp_repo.path, "log", "-1", fmt, shas[0]) == git(
        tmp_repo.path, "log", "-1", fmt, ends[0]
    )
    last = git(tmp_repo.path, "log", "-1", "--format=%B", shas[-1])
    assert last == "chore: drop report"


def test_rewrite_is_deterministic(tmp_repo: Repo) -> None:
    a = rewrite(tmp_repo.path, "c0", "main", "main", "tail", "a")
    b = rewrite(tmp_repo.path, "c0", "main", "main", "tail", "b")
    assert a == b


def test_fork_is_ancestor_of_result(tmp_repo: Repo) -> None:
    shas = rewrite(tmp_repo.path, "c0", "main", "main", "tail", "new")
    git(tmp_repo.path, "merge-base", "--is-ancestor", "c0", "new")
    assert git(tmp_repo.path, "rev-parse", f"{shas[0]}^") == git(
        tmp_repo.path, "rev-parse", "c0"
    )


def test_merge_commits_are_skipped(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "merge")
    repo.commit("chore: initial", {"README.md": "hello\n"})
    git(repo.path, "tag", "c0")
    repo.commit("feat(chat): stream answers", {"backend/chat/a.py": "a\n"})
    git(repo.path, "checkout", "-q", "-b", "side")
    repo.commit("feat(side): side work", {"backend/side/s.py": "s\n"})
    git(repo.path, "checkout", "-q", "main")
    repo.commit("docs(report): results table", {"docs/report/x.tex": "x\n"})
    repo.merge("side", "Merge branch side")
    repo.commit("feat(auth): otp login", {"backend/auth/d.py": "d\n"})
    segs = segments(repo.path, "c0", "main")
    assert shape(segs) == [
        ("app", "chat", 1),
        ("research", "report", 1),
        ("app", "auth", 1),
    ]
    shas = rewrite(repo.path, "c0", "main", "main", "main", "new")
    assert repo.tree("new") == repo.tree("main")
    bodies = git(repo.path, "log", "--format=%B", "c0..new")
    assert "side work" not in bodies
    assert "Merge" not in bodies
    assert len(shas) == 3
    files = git(repo.path, "ls-tree", "-r", "--name-only", shas[1])
    assert "backend/side/s.py" in files


def test_reorder_moves_segment_when_files_do_not_conflict(tmp_repo: Repo) -> None:
    grouped = group_by_scope(segments(tmp_repo.path, "c0", "main"))
    assert shape(grouped) == [
        ("app", "chat", 3),
        ("research", "report", 1),
        ("app", "auth", 2),
    ]
    shas = rewrite(tmp_repo.path, "c0", "main", "main", "tail", "new", reorder=True)
    assert len(shas) == 5
    assert tmp_repo.tree("new") == tmp_repo.tree("tail")
    chat = git(tmp_repo.path, "ls-tree", "-r", "--name-only", shas[0]).splitlines()
    assert "frontend/chat/c.tsx" in chat
    assert "docs/report/x.tex" not in chat
    assert tmp_repo.tree(shas[2]) == tmp_repo.tree("main")
    body = git(tmp_repo.path, "log", "-1", "--format=%b", shas[0])
    assert "- feat(chat): chat page" in body


def test_reorder_refuses_when_files_conflict(conflict_repo: Repo) -> None:
    segs = segments(conflict_repo.path, "c0", "main")
    assert group_by_scope(segs) == segs
    shas = rewrite(
        conflict_repo.path, "c0", "main", "main", "tail", "new", reorder=True
    )
    assert conflict_repo.tree("new") == conflict_repo.tree("tail")
    assert len(shas) == 6


def test_refuses_branch_checked_out(tmp_repo: Repo) -> None:
    with pytest.raises(SystemExit):
        rewrite(tmp_repo.path, "c0", "main", "main", "tail", "main")


def test_cli_prints_table(tmp_repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    main(
        [
            "--repo",
            str(tmp_repo.path),
            "--fork",
            "c0",
            "--old-ref",
            "main",
            "--tail-base",
            "main",
            "--tail-ref",
            "tail",
            "--branch",
            "new",
            "--reorder",
        ]
    )
    out = capsys.readouterr().out
    assert "feat(chat): stream answers" in out
    assert git(tmp_repo.path, "rev-parse", "--short=12", "new") in out
    assert len(out.strip().splitlines()) == 1 + 5


def test_fork_merged_in_from_side(tmp_path: Path) -> None:
    """The fork sits on another branch and reaches old_ref through a merge: early
    commits are rebuilt on top of the fork, a conflicting file keeps the branch's
    version until the old merge resolves it, and later trees are the old ones."""
    repo = Repo(tmp_path / "side")
    repo.commit("chore: initial", {"README.md": "hello\n", "paper.tex": "v0\n"})
    git(repo.path, "checkout", "-q", "-b", "paper")
    repo.commit("docs(paper): camera ready", {"paper.tex": "camera\n", "p.txt": "p\n"})
    git(repo.path, "tag", "c0")
    git(repo.path, "checkout", "-q", "main")
    repo.commit("docs(paper): v2 draft", {"paper.tex": "v2\n"})
    repo.commit("feat(chat): stream answers", {"backend/chat/a.py": "a\n"})
    git(repo.path, "merge", "-q", "-s", "ours", "--no-commit", "paper", env=repo._env())
    (repo.path / "p.txt").write_text("p\n")
    (repo.path / "paper.tex").write_text("merged\n")
    git(repo.path, "add", "p.txt", "paper.tex")
    git(repo.path, "commit", "-q", "-m", "Merge paper", env=repo._env())
    repo.commit("feat(auth): otp login", {"backend/auth/d.py": "d\n"})
    shas = rewrite(repo.path, "c0", "main", "main", "main", "new")
    assert len(shas) == 3
    assert git(repo.path, "rev-parse", f"{shas[0]}^") == git(
        repo.path, "rev-parse", "c0"
    )
    first = git(repo.path, "ls-tree", "-r", "--name-only", shas[0]).splitlines()
    assert "p.txt" in first
    assert git(repo.path, "show", f"{shas[0]}:paper.tex") == "v2"
    assert git(repo.path, "show", f"{shas[1]}:paper.tex") == "merged"
    assert git(repo.path, "show", f"{shas[1]}:backend/chat/a.py") == "a"
    assert repo.tree("new") == repo.tree("main")


def test_scope_skips_generic_second_level_dirs(tmp_repo: Repo) -> None:
    tmp_repo.commit(
        "Revert something",
        {"pharma-lab/src/a.py": "1\n", "pharma-lab/src/b.py": "2\n"},
    )
    assert shape(segments(tmp_repo.path, "c0", "main"))[-1] == (
        "research",
        "pharma-lab",
        1,
    )
