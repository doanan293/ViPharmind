"""Push the backend's production settings to the Vercel project and redeploy it.

Every PHARMA_* variable in backend/.env.production, and its CRON_SECRET (the name Vercel
Cron reads), becomes an encrypted Production environment variable of the `vipharmind-api`
project, plus the settings below that only apply to Vercel. Needs a logged-in Vercel CLI (`vercel login`).

    uv run python devops/vercel/sync_env.py
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "backend" / ".env.production"
# The CLI selects a project by id, not by name, through VERCEL_PROJECT_ID.
PROJECT_ID = "prj_SskPeExKM3zehi0Vr3f4Lt1TKjW4"  # vipharmind-api
PRODUCTION_URL = "https://vipharmind-api.vercel.app"

# Vercel overwrites X-Forwarded-For with the caller's address, and the frontend proxy adds one
# more hop through the shared secret (measured on 2026-10-12). A function may freeze once it
# has answered, so publish jobs run inside the request, within the 300 s maxDuration that
# the default PHARMA_JOBS__STALE_AFTER_SECONDS (330) outlasts.
VERCEL_SETTINGS = {
    "PHARMA_API__TRUSTED_PROXY_HOPS": "1",
    "PHARMA_JOBS__DISPATCHER": "inline",
    "PHARMA_AUTH__FRONTEND_URL": "https://vipharmind.vercel.app",
    "PHARMA_SMS__PROVIDER": "none",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def linked_team() -> str | None:
    link = ROOT / "frontend" / ".vercel" / "project.json"
    return json.loads(link.read_text())["orgId"] if link.exists() else None


def vercel(*args: str, project: str) -> None:
    # VERCEL_PROJECT_ID selects the project without a .vercel link in the repository.
    env = os.environ | {"VERCEL_PROJECT_ID": project}
    # No stdin: a CLI prompt fails the run instead of waiting forever.
    subprocess.run(
        ["vercel", *args], check=True, env=env, cwd=ROOT, stdin=subprocess.DEVNULL
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=PROJECT_ID, help="Vercel project id")
    parser.add_argument(
        "--team",
        default=os.environ.get("VERCEL_ORG_ID") or linked_team(),
        help="Vercel team id; defaults to the one frontend/ is linked to",
    )
    parser.add_argument("--no-redeploy", action="store_true")
    args = parser.parse_args()
    if args.team:
        os.environ["VERCEL_ORG_ID"] = args.team

    env = read_env(ENV_FILE)
    variables = {
        k: v for k, v in env.items() if k.startswith("PHARMA_") or k == "CRON_SECRET"
    } | VERCEL_SETTINGS
    for key, value in sorted(variables.items()):
        vercel(
            "env", "add", key, "production", "--value", value, "--sensitive",
            "--force", "--yes", project=args.project,
        )  # fmt: skip
    print(f"{len(variables)} variables set on {args.project}")
    if not args.no_redeploy:
        vercel(
            "redeploy", PRODUCTION_URL, "--target", "production",
            project=args.project,
        )  # fmt: skip


if __name__ == "__main__":
    main()
