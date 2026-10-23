from __future__ import annotations

import hashlib
import http.server
import io
import os
import stat
import tarfile
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pharma_lab.e2e.proxy_kernel import (
    PROXY_API_KEY,
    PROXY_PORT,
    PROXY_SHA256,
    PROXY_VERSION,
    fetch_proxy,
    install_credentials,
    proxy_release_url,
    start_proxy,
    write_proxy_config,
)

TEMPLATE = """\
# CLIProxyAPI configuration
host: ""
port: 8317
auth-dir: "/root/.cli-proxy-api"
api-keys:
  - "something-else"
debug: false
remote-management:
  allow-remote: true
  secret-key: "do-not-keep"
payload:
  default:
    - models:
        - name: "gemini-3*"
      params:
        thinkingLevel: high
request-retry: 0
"""


def test_release_url_is_pinned() -> None:
    assert proxy_release_url() == (
        "https://github.com/router-for-me/CLIProxyAPI/releases/download/"
        f"v{PROXY_VERSION}/CLIProxyAPI_{PROXY_VERSION}_linux_amd64.tar.gz"
    )
    assert PROXY_VERSION == "8.0.28"
    assert len(PROXY_SHA256) == 64


def test_config_forces_localhost_binding(tmp_path: Path) -> None:
    template = tmp_path / "template.yaml"
    template.write_text(TEMPLATE, encoding="utf-8")

    target = write_proxy_config(template, tmp_path / "config.yaml", tmp_path / "auth")
    text = target.read_text(encoding="utf-8")

    assert 'host: "127.0.0.1"' in text
    assert f"port: {PROXY_PORT}" in text
    assert f'auth-dir: "{tmp_path / "auth"}"' in text
    assert f'  - "{PROXY_API_KEY}"' in text
    # Provider settings such as the thinking payload survive; the rest is replaced.
    assert "thinkingLevel: high" in text
    assert "request-retry: 0" in text
    for dropped in ("something-else", "do-not-keep", "allow-remote", "/root/"):
        assert dropped not in text
    assert text.count("host:") == 1
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_config_without_a_template_is_the_minimal_localhost_config(
    tmp_path: Path,
) -> None:
    target = write_proxy_config(None, tmp_path / "config.yaml", tmp_path / "auth")

    text = target.read_text(encoding="utf-8")
    assert 'host: "127.0.0.1"' in text
    assert PROXY_API_KEY in text


def test_credentials_are_copied_with_private_modes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "claude-a@example.com.json").write_text('{"type": "claude"}')
    (source / "antigravity-b.json").write_text('{"type": "antigravity"}')
    (source / "proxy-config.yaml").write_text("host: x")
    auth = tmp_path / "auth"

    names = install_credentials(source, auth)

    assert names == ["antigravity-b.json", "claude-a@example.com.json"]
    assert stat.S_IMODE(os.stat(auth).st_mode) == 0o700
    for name in names:
        assert stat.S_IMODE(os.stat(auth / name).st_mode) == 0o600
    assert not (auth / "proxy-config.yaml").exists()


def make_release(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, payload in (("CLIProxyAPI", b"#!/bin/sh\n"), ("README.md", b"hi")):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_fetch_proxy_verifies_the_checksum_and_extracts_the_binary(
    tmp_path: Path,
) -> None:
    archive, digest = make_release(tmp_path)

    binary = fetch_proxy(tmp_path / "bin", url=archive.as_uri(), sha256=digest)

    assert binary.name == "CLIProxyAPI"
    assert os.access(binary, os.X_OK)
    assert sorted(p.name for p in (tmp_path / "bin").iterdir()) == ["CLIProxyAPI"]


def test_fetch_proxy_refuses_a_different_archive(tmp_path: Path) -> None:
    archive, _ = make_release(tmp_path)

    with pytest.raises(RuntimeError, match="checksum"):
        fetch_proxy(tmp_path / "bin", url=archive.as_uri(), sha256="0" * 64)
    assert not (tmp_path / "bin" / "CLIProxyAPI").exists()


@contextmanager
def models_server(ready_after: int) -> Generator[int]:
    seen = {"count": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen["count"] += 1
            authorised = self.headers.get("Authorization") == f"Bearer {PROXY_API_KEY}"
            ready = self.path == "/v1/models" and authorised
            self.send_response(200 if ready and seen["count"] > ready_after else 503)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


class Process:
    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code
        self.terminated = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


def test_start_proxy_waits_for_models_endpoint(tmp_path: Path) -> None:
    launched: list[list[str]] = []
    process = Process()

    def popen(command: list[str], **_kwargs: object) -> Process:
        launched.append(command)
        return process

    with models_server(ready_after=2) as port:
        start_proxy(
            tmp_path / "CLIProxyAPI",
            tmp_path / "config.yaml",
            port=port,
            wait_seconds=10,
            poll_seconds=0.01,
            popen=popen,
            log_path=tmp_path / "proxy.log",
        )

    assert launched == [
        [str(tmp_path / "CLIProxyAPI"), "-config", str(tmp_path / "config.yaml")]
    ]
    assert not process.terminated


def test_start_proxy_stops_it_when_it_never_answers(tmp_path: Path) -> None:
    process = Process()

    with (
        models_server(ready_after=10_000) as port,
        pytest.raises(RuntimeError, match="did not answer"),
    ):
        start_proxy(
            tmp_path / "p",
            tmp_path / "c",
            port=port,
            wait_seconds=0.2,
            poll_seconds=0.01,
            popen=lambda *_a, **_k: process,
            log_path=tmp_path / "proxy.log",
        )

    assert process.terminated


def test_start_proxy_reports_an_early_exit(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="exited with 3"):
        start_proxy(
            tmp_path / "p",
            tmp_path / "c",
            port=1,
            wait_seconds=5,
            poll_seconds=0.01,
            popen=lambda *_a, **_k: Process(exit_code=3),
            log_path=tmp_path / "proxy.log",
        )
