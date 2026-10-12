"""Get the refresh token that lets the backend send mail through the Gmail API.

The OAuth client is a Desktop client in the shared Google Cloud project `andimus`. Put its
PHARMA_EMAIL__GMAIL_CLIENT_ID and PHARMA_EMAIL__GMAIL_CLIENT_SECRET in
backend/.env.production, run this from the repository root, open the printed URL, sign in
as the sending account and allow sending. The refresh token is written back to that file.

    uv run --with google-auth-oauthlib python devops/google/gmail_refresh_token.py
"""

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ENV_FILE = Path(__file__).resolve().parents[2] / "backend" / ".env.production"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def write_env(path: Path, updates: dict[str, str]) -> None:
    lines = [
        line
        for line in path.read_text().splitlines()
        if line.split("=", 1)[0].strip() not in updates
    ]
    lines += [f"{key}={value}" for key, value in updates.items()]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--account", help="the Gmail address to pre-select")
    args = parser.parse_args()

    env = read_env(ENV_FILE)
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": env["PHARMA_EMAIL__GMAIL_CLIENT_ID"],
                "client_secret": env["PHARMA_EMAIL__GMAIL_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        SCOPES,
    )
    # prompt=consent makes Google return a refresh token even after an earlier consent.
    extra = {"prompt": "consent"} | (
        {"login_hint": args.account} if args.account else {}
    )
    credentials = flow.run_local_server(port=args.port, open_browser=False, **extra)
    if not credentials.refresh_token:
        raise SystemExit("Google returned no refresh token; run again")
    write_env(
        ENV_FILE,
        {
            "PHARMA_EMAIL__PROVIDER": "gmail",
            "PHARMA_EMAIL__GMAIL_REFRESH_TOKEN": credentials.refresh_token,
        },
    )
    print(f"refresh token written to {ENV_FILE}")


if __name__ == "__main__":
    main()
