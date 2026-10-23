"""`cli-proxy-api` inside a Kaggle kernel, for the Gemini and Claude presets.

The proxy listens on 127.0.0.1 only and calls out to the providers with the OAuth files
the run uploaded to a private dataset. Nothing here reads a credential: files are copied
by name with private modes. Stdlib only: the kernel's orchestrating process imports this
module before the backend's dependencies are installed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pharma_lab.e2e.llm_presets import PROXY_API_KEY

PROXY_VERSION = "8.0.28"
# From the release's checksums.txt (and GitHub's asset digest, which agree).
PROXY_SHA256 = "1644171946913c858842081053abb6f67234bb41ce2691602bf834361293c17f"
PROXY_PORT = 8317
# The member of the release archive that is the program (checked against the real v8.0.28).
PROXY_BINARY = "cli-proxy-api"
CONFIG_NAME = "proxy-config.yaml"
RELEASES = "https://github.com/router-for-me/CLIProxyAPI/releases/download"
# Top-level settings the kernel decides itself, whatever the template says: where to
# listen, where the credentials are, the local key, and no remote management API.
FORCED_KEYS = frozenset({"host", "port", "auth-dir", "api-keys", "remote-management"})


class Process(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


def proxy_release_url(version: str = PROXY_VERSION) -> str:
    return f"{RELEASES}/v{version}/CLIProxyAPI_{version}_linux_amd64.tar.gz"


def _top_level_key(line: str) -> str | None:
    if not line or line[0] in " \t#-":
        return None
    return line.partition(":")[0].strip()


def without_forced_keys(text: str) -> list[str]:
    """The lines of a proxy config minus the settings the kernel decides itself (its
    local keys and management secret included)."""
    kept: list[str] = []
    dropping = False
    for line in text.splitlines():
        key = _top_level_key(line)
        if key is not None:
            dropping = key in FORCED_KEYS
        if not dropping:
            kept.append(line)
    return kept


def write_proxy_config(template: Path | None, target: Path, auth_dir: Path) -> Path:
    """The template minus the settings the kernel forces, behind the forced ones."""
    kept = (
        []
        if template is None
        else without_forced_keys(template.read_text(encoding="utf-8"))
    )
    forced = [
        'host: "127.0.0.1"',
        f"port: {PROXY_PORT}",
        f'auth-dir: "{auth_dir}"',
        "api-keys:",
        f'  - "{PROXY_API_KEY}"',
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join([*forced, *kept]) + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target


def install_credentials(source: Path, auth_dir: Path) -> list[str]:
    """Copy the credential files (`*.json`) into a private directory; returns the names."""
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_dir.chmod(0o700)
    names = []
    for path in sorted(source.glob("*.json")):
        destination = auth_dir / path.name
        shutil.copyfile(path, destination)
        destination.chmod(0o600)
        names.append(path.name)
    return names


def fetch_proxy(
    directory: Path, *, url: str | None = None, sha256: str = PROXY_SHA256
) -> Path:
    """Download the release, check its sha256 and extract only the binary."""
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "release.tar.gz"
    digest = hashlib.sha256()
    with (
        urllib.request.urlopen(url or proxy_release_url(), timeout=120) as response,
        archive.open("wb") as handle,
    ):
        for block in iter(lambda: response.read(1 << 20), b""):
            digest.update(block)
            handle.write(block)
    try:
        if digest.hexdigest() != sha256:
            raise RuntimeError(
                f"cli-proxy-api checksum mismatch: {digest.hexdigest()} != {sha256}"
            )
        binary = directory / PROXY_BINARY
        with tarfile.open(archive) as tar:
            member = tar.getmember(PROXY_BINARY)
            source = tar.extractfile(member)
            if source is None:
                raise RuntimeError(f"{PROXY_BINARY} is not a file in the release")
            binary.write_bytes(source.read())
        binary.chmod(0o755)
        return binary
    finally:
        archive.unlink(missing_ok=True)


def _answers(port: int) -> bool:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/models",
        headers={"Authorization": f"Bearer {PROXY_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        error.close()
        return False
    except (urllib.error.URLError, OSError):
        return False


def start_proxy(
    binary: Path,
    config: Path,
    *,
    port: int = PROXY_PORT,
    wait_seconds: float = 60,
    poll_seconds: float = 1.0,
    popen: Callable[..., Process] = subprocess.Popen,
    log_path: Path | None = None,
) -> Process:
    """Start the proxy and wait until `/v1/models` answers on localhost. Its output goes
    to a file outside the artifact: it can name the accounts it holds."""
    destination = log_path or Path("/tmp") / "cli-proxy-api.log"
    with destination.open("ab") as log:
        os.chmod(destination, 0o600)
        process = popen(
            [str(binary), "-config", str(config)], stdout=log, stderr=subprocess.STDOUT
        )
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"cli-proxy-api exited with {code} before it was ready")
        if _answers(port):
            return process
        time.sleep(poll_seconds)
    process.terminate()
    raise RuntimeError(
        f"cli-proxy-api did not answer on 127.0.0.1:{port} within {wait_seconds:.0f} s"
    )
