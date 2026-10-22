"""A Kaggle kernel never exposes anything: no tunnel, no listener outside localhost.

An account was banned once for a notebook that opened a public tunnel to serve a model.
Everything that runs in a kernel talks over 127.0.0.1 and downloads only.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "pharma_lab"

TUNNEL_TOOLS = re.compile(
    r"cloudflared|trycloudflare|ngrok|localtunnel|pinggy|serveo|bore\.pub|\btunnel",
    re.IGNORECASE,
)
SERVER_HOST = re.compile(r'"--host",\s*"([^"]*)"')


def _sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_no_source_opens_a_tunnel() -> None:
    found = [
        f"{path.relative_to(SRC).as_posix()}:{number}"
        for path in _sources()
        for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1)
        if TUNNEL_TOOLS.search(line)
    ]

    assert found == []


def test_no_source_listens_on_every_interface() -> None:
    found = [
        path.relative_to(SRC).as_posix()
        for path in _sources()
        if "0.0.0.0" in path.read_text("utf-8")
    ]

    assert found == []


def test_every_model_server_binds_to_localhost() -> None:
    hosts = {
        path.relative_to(SRC).as_posix(): SERVER_HOST.findall(path.read_text("utf-8"))
        for path in _sources()
    }
    hosts = {path: values for path, values in hosts.items() if values}

    assert hosts, "no llama-server command found: the check would pass vacuously"
    assert all(set(values) == {"127.0.0.1"} for values in hosts.values())
