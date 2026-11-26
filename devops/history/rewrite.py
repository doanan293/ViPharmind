"""Rewrite a branch's private history into one commit per feature run.

Walks the first-parent history of ``fork..old_ref``, groups consecutive commits
of the same kind (app or research) and scope into segments, writes one commit
per segment on top of ``fork``, then replays every first-parent commit of
``tail_base..tail_ref`` with its own tree, so the final tree is ``tail_ref``'s.
Only objects and one branch ref are written; no working tree is touched.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

GENERIC_DIRS = {"src", "tests", "test", "docs", "app", "lib"}
APP_PREFIXES = ("backend/", "frontend/", "devops/", "scripts/")
SUBJECT = re.compile(r"^(?P<type>[\w-]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<desc>.+)$")
AI_LINE = re.compile(
    r"^\s*(co-authored-by:.*(claude|anthropic|openai|copilot|gemini)"
    r"|.*generated with \[?claude)",
    re.IGNORECASE,
)
ZERO = "0" * 40
IDENTITY = "%an%x00%ae%x00%ad%x00%cn%x00%ce%x00%cd"


@dataclass(frozen=True)
class Segment:
    """Consecutive first-parent commits sharing kind and scope.

    ``end`` is the last commit of the segment, merges folded in included;
    ``commits`` and ``subjects`` hold the non-merge commits only; ``runs`` are the
    contiguous (first, last) ranges of the old history the segment is made of.
    """

    start: str
    end: str
    kind: str
    scope: str
    n: int
    commits: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    runs: tuple[tuple[str, str], ...] = ()
    files: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NewCommit:
    sha: str
    subject: str
    folded: int


def git(
    repo: Path, *args: str, stdin: str | None = None, env: dict | None = None
) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def git_ok(repo: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), *args]).returncode == 0


def tree_of(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", f"{ref}^{{tree}}").strip()


class Rebased:
    """Trees of old commits as they look on top of ``fork``.

    A commit that already contains ``fork`` keeps its own tree. An older one (the
    branch merged ``fork`` in later) gets a 3-way merge of ``fork`` and itself;
    a path that conflicts takes the commit's whole version, and the old merge
    that brought ``fork`` in later applies its own resolution.
    """

    def __init__(self, repo: Path, fork: str) -> None:
        self.repo = repo
        self.fork = git(repo, "rev-parse", f"{fork}^{{commit}}").strip()
        self.trees: dict[str, str] = {}

    def tree(self, rev: str) -> str:
        sha = git(self.repo, "rev-parse", f"{rev}^{{commit}}").strip()
        if sha not in self.trees:
            self.trees[sha] = self._compute(sha)
        return self.trees[sha]

    def _compute(self, sha: str) -> str:
        repo = self.repo
        if git_ok(repo, "merge-base", "--is-ancestor", self.fork, sha):
            return tree_of(repo, sha)
        base = git(repo, "merge-base", self.fork, sha).strip()
        merged = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "merge-tree",
                "--write-tree",
                "-z",
                "--name-only",
                "--no-messages",
                "-X",
                "no-renames",
                f"--merge-base={base}",
                self.fork,
                sha,
            ],
            capture_output=True,
            text=True,
        )
        if merged.returncode not in (0, 1):
            raise SystemExit(f"merge-tree {self.fork} {sha}: {merged.stderr.strip()}")
        tree, *conflicted = [p for p in merged.stdout.split("\0") if p]
        if merged.returncode == 0:
            return tree
        paths = sorted(set(conflicted))
        env = {"GIT_LITERAL_PATHSPECS": "1"}
        ours = git(repo, "ls-tree", "-z", "--full-tree", sha, "--", *paths, env=env)
        entries = {}
        for record in filter(None, ours.split("\0")):
            meta, path = record.split("\t", 1)
            mode, _, blob = meta.split()
            entries[path] = f"{mode} {blob}\t{path}"
        lines = [entries.get(p, f"0 {ZERO}\t{p}") for p in paths]
        with tempfile.TemporaryDirectory() as tmp:
            env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
            git(repo, "read-tree", tree, env=env)
            stdin = "\0".join(lines) + "\0"
            git(repo, "update-index", "-z", "--index-info", stdin=stdin, env=env)
            return git(repo, "write-tree", env=env).strip()

    def diff(self, first: str, last: str, *flags: str) -> str:
        """Raw diff from the parent of ``first`` to ``last``, both rebased."""
        old, new = self.tree(f"{first}^"), self.tree(last)
        return git(self.repo, "diff-tree", "-r", "-z", "--no-renames", *flags, old, new)

    def files(self, sha: str) -> list[str]:
        return [p for p in self.diff(sha, sha, "--name-only").split("\0") if p]


def is_app(path: str) -> bool:
    return path.startswith(APP_PREFIXES) or path.startswith("compose")


def kind_of(files: list[str]) -> str:
    return "app" if 2 * sum(map(is_app, files)) > len(files) else "research"


def directory_of(path: str) -> str:
    """Second-level directory, or the first-level one when the second is generic."""
    parts = path.split("/")
    if len(parts) > 2 and parts[1] not in GENERIC_DIRS:
        return parts[1]
    return parts[0] if len(parts) > 1 else "repo"


def scope_of(subject: str, files: list[str]) -> str:
    match = SUBJECT.match(subject)
    if match and match["scope"]:
        return match["scope"]
    dirs = Counter(map(directory_of, files))
    if not dirs:
        return "repo"
    return min(dirs, key=lambda d: (-dirs[d], d))


def first_parent_commits(
    repo: Path, base: str, ref: str
) -> list[tuple[str, bool, str]]:
    """(sha, is_merge, subject) of first-parent ``base..ref``, oldest first."""
    out = git(
        repo,
        "log",
        "--first-parent",
        "--reverse",
        "--format=%H%x00%P%x00%s",
        f"{base}..{ref}",
    )
    rows = []
    for line in out.splitlines():
        sha, parents, subject = line.split("\0", 2)
        rows.append((sha, len(parents.split()) > 1, subject))
    return rows


def segments(repo: Path, fork: str, old_ref: str) -> list[Segment]:
    """Group first-parent ``fork..old_ref`` into segments of one kind and scope.

    Merge commits are not classified nor listed; their changes (against their
    first parent) are folded into the segment before them, or into the first
    segment when they come first.
    """
    rebased = Rebased(repo, fork)
    result: list[Segment] = []
    current: Segment | None = None
    pending_start: str | None = None
    pending_files: set[str] = set()
    for sha, merge, subject in first_parent_commits(repo, fork, old_ref):
        files = rebased.files(sha)
        if merge:
            if current is None:
                pending_start = pending_start or sha
                pending_files.update(files)
            else:
                first, _ = current.runs[0]
                current = replace(
                    current,
                    end=sha,
                    runs=((first, sha),),
                    files=current.files | set(files),
                )
            continue
        kind, scope = kind_of(files), scope_of(subject, files)
        if current and (current.kind, current.scope) == (kind, scope):
            first, _ = current.runs[0]
            current = replace(
                current,
                end=sha,
                n=current.n + 1,
                commits=(*current.commits, sha),
                subjects=(*current.subjects, subject),
                runs=((first, sha),),
                files=current.files | set(files),
            )
            continue
        if current:
            result.append(current)
        start = pending_start or sha
        current = Segment(
            start=start,
            end=sha,
            kind=kind,
            scope=scope,
            n=1,
            commits=(sha,),
            subjects=(subject,),
            runs=((start, sha),),
            files=frozenset(pending_files | set(files)),
        )
        pending_start, pending_files = None, set()
    if current:
        result.append(current)
    return result


def group_by_scope(segs: list[Segment]) -> list[Segment]:
    """Move each segment next to the nearest earlier segment of the same kind and
    scope, and merge them, when it touches no file of the segments in between.
    Disjoint files mean the moved diffs apply unchanged at the new place."""
    out: list[Segment] = []
    for seg in segs:
        key = (seg.kind, seg.scope)
        target = next(
            (
                i
                for i in range(len(out) - 1, -1, -1)
                if (out[i].kind, out[i].scope) == key
            ),
            None,
        )
        if target is None or any(
            not o.files.isdisjoint(seg.files) for o in out[target + 1 :]
        ):
            out.append(seg)
            continue
        host = out[target]
        out[target] = replace(
            host,
            end=seg.end,
            n=host.n + seg.n,
            commits=host.commits + seg.commits,
            subjects=host.subjects + seg.subjects,
            runs=host.runs + seg.runs,
            files=host.files | seg.files,
        )
    return out


def clean_message(message: str) -> str:
    lines = [line for line in message.splitlines() if not AI_LINE.match(line)]
    return "\n".join(lines).strip() + "\n"


def segment_message(seg: Segment) -> str:
    prefix = "feat" if seg.kind == "app" else "docs"
    parsed = [SUBJECT.match(s) for s in seg.subjects]
    preferred = [m for m in parsed if m and m["type"] == prefix]
    any_parsed = [m for m in parsed if m]
    if preferred or any_parsed:
        summary = (preferred or any_parsed)[0]["desc"]
    else:
        summary = seg.subjects[0]
    body = "\n".join(f"- {s}" for s in seg.subjects)
    return clean_message(f"{prefix}({seg.scope}): {summary}\n\n{body}")


def identity_env(repo: Path, sha: str) -> dict[str, str]:
    fields = git(repo, "log", "-1", "--date=raw", f"--format={IDENTITY}", sha).rstrip(
        "\n"
    )
    keys = (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_DATE",
    )
    return dict(zip(keys, fields.split("\0"), strict=True))


def commit_tree(
    repo: Path, tree: str, parent: str, message: str, identity_of: str
) -> str:
    env = identity_env(repo, identity_of)
    args = ("commit-tree", "--no-gpg-sign", tree, "-p", parent, "-F", "-")
    return git(repo, *args, stdin=message, env=env).strip()


class TreeBuilder:
    """Applies old diffs to a temporary index, checking each one applies exactly."""

    def __init__(self, rebased: Rebased, base: str, index: Path) -> None:
        repo = self.repo = rebased.repo
        self.rebased = rebased
        self.env = {"GIT_INDEX_FILE": str(index)}
        git(repo, "read-tree", base, env=self.env)
        listing = git(repo, "ls-tree", "-r", "-z", "--full-tree", base)
        self.entries: dict[str, tuple[str, str]] = {}
        for record in filter(None, listing.split("\0")):
            meta, path = record.split("\t", 1)
            mode, _, sha = meta.split()
            self.entries[path] = (mode, sha)

    def apply(self, first: str, last: str) -> None:
        raw = self.rebased.diff(first, last)
        tokens = raw.split("\0")
        lines = []
        for meta, path in zip(tokens[0:-1:2], tokens[1::2], strict=True):
            old_mode, new_mode, old_sha, new_sha, _ = meta.lstrip(":").split()
            expected = None if old_sha == ZERO else (old_mode, old_sha)
            if self.entries.get(path) != expected:
                raise SystemExit(f"{first}..{last} does not apply at {path}")
            if new_sha == ZERO:
                del self.entries[path]
                lines.append(f"0 {ZERO}\t{path}")
            else:
                self.entries[path] = (new_mode, new_sha)
                lines.append(f"{new_mode} {new_sha}\t{path}")
        if lines:
            stdin = "\0".join(lines) + "\0"
            git(
                self.repo,
                "update-index",
                "-z",
                "--index-info",
                stdin=stdin,
                env=self.env,
            )

    def write(self) -> str:
        return git(self.repo, "write-tree", env=self.env).strip()


def check_branch(repo: Path, branch: str) -> None:
    git(repo, "check-ref-format", "--branch", branch)
    worktrees = git(repo, "worktree", "list", "--porcelain").splitlines()
    if f"branch refs/heads/{branch}" in worktrees:
        raise SystemExit(f"{branch} is checked out in a worktree; pick another branch")


def build(
    repo: Path,
    fork: str,
    old_ref: str,
    tail_base: str,
    tail_ref: str,
    branch: str,
    reorder: bool = False,
) -> list[NewCommit]:
    check_branch(repo, branch)
    git(repo, "merge-base", "--is-ancestor", fork, old_ref)
    git(repo, "merge-base", "--is-ancestor", tail_base, tail_ref)
    segs = segments(repo, fork, old_ref)
    if reorder:
        segs = group_by_scope(segs)
    parent = git(repo, "rev-parse", f"{fork}^{{commit}}").strip()
    made: list[NewCommit] = []
    with tempfile.TemporaryDirectory() as tmp:
        rebased = Rebased(repo, fork)
        builder = TreeBuilder(rebased, parent, Path(tmp) / "index")
        for seg in segs:
            for first, last in seg.runs:
                builder.apply(first, last)
            tree = builder.write()
            if not reorder and tree != rebased.tree(seg.end):
                raise SystemExit(f"segment ending {seg.end} rebuilt a different tree")
            message = segment_message(seg)
            parent = commit_tree(repo, tree, parent, message, seg.commits[-1])
            made.append(NewCommit(parent, message.splitlines()[0], seg.n))
        if segs and builder.write() != tree_of(repo, old_ref):
            raise SystemExit(f"segments do not rebuild the tree of {old_ref}")
    for sha, _, _ in first_parent_commits(repo, tail_base, tail_ref):
        message = clean_message(git(repo, "log", "-1", "--format=%B", sha))
        parent = commit_tree(repo, tree_of(repo, sha), parent, message, sha)
        made.append(NewCommit(parent, message.splitlines()[0], 1))
    if tree_of(repo, parent) != tree_of(repo, tail_ref):
        raise SystemExit(f"final tree differs from {tail_ref}")
    git(repo, "update-ref", f"refs/heads/{branch}", parent)
    return made


def rewrite(
    repo: Path,
    fork: str,
    old_ref: str,
    tail_base: str,
    tail_ref: str,
    branch: str,
    reorder: bool = False,
) -> list[str]:
    """Build ``refs/heads/<branch>`` and return the new SHAs, oldest first."""
    made = build(repo, fork, old_ref, tail_base, tail_ref, branch, reorder)
    return [c.sha for c in made]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--fork", required=True)
    parser.add_argument("--old-ref", required=True)
    parser.add_argument("--tail-base", required=True)
    parser.add_argument("--tail-ref", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--reorder", action="store_true")
    args = parser.parse_args(argv)
    made = build(
        args.repo,
        args.fork,
        args.old_ref,
        args.tail_base,
        args.tail_ref,
        args.branch,
        args.reorder,
    )
    print(f"{'sha':<12}  {'old':>3}  subject")
    for c in made:
        print(f"{c.sha[:12]}  {c.folded:>3}  {c.subject}")


if __name__ == "__main__":
    main(sys.argv[1:])
