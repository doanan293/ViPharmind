"""Create or update the backend web service on Render and deploy it.

Every PHARMA_* variable in backend/.env.production becomes a service environment variable,
plus the settings below that only apply to Render. The Render API key is read from
RENDER_API_KEY in the same gitignored file.

    uv run --with httpx python devops/render/configure.py
"""

import argparse
from pathlib import Path

import httpx

API = "https://api.render.com/v1"
ENV_FILE = Path(__file__).resolve().parents[2] / "backend" / ".env.production"
REPO = "https://github.com/doanan293/vipharma-rag"

# Render terminates TLS and forwards to $PORT, which the settings read. Its edge appends three X-Forwarded-For
# entries (the caller seen by Cloudflare, the Cloudflare node, Render's internal proxy), measured
# on 2026-10-11; the Vercel proxy adds one more through the shared secret. Publish jobs run
# inside the API process because the free plan has no background workers.
RENDER_SETTINGS = {
    "PHARMA_API__HOST": "0.0.0.0",
    "PHARMA_API__TRUSTED_PROXY_HOPS": "3",
    "PHARMA_JOBS__DISPATCHER": "inprocess",
    "PHARMA_AUTH__FRONTEND_URL": "https://vipharmind.vercel.app",
    "PHARMA_SMS__PROVIDER": "none",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def find_service(client: httpx.Client, name: str) -> dict | None:
    for item in (
        client.get("/services", params={"name": name, "limit": 20})
        .raise_for_status()
        .json()
    ):
        if item["service"]["name"] == name:
            return item["service"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="vipharmind-api")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args()

    env = read_env(ENV_FILE)
    variables = {
        k: v for k, v in env.items() if k.startswith("PHARMA_")
    } | RENDER_SETTINGS
    env_vars = [{"key": k, "value": v} for k, v in sorted(variables.items())]

    with httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {env['RENDER_API_KEY']}"},
        timeout=60,
    ) as client:
        service = find_service(client, args.name)
        if service is None:
            owner_id = client.get("/owners").raise_for_status().json()[0]["owner"]["id"]
            service = (
                client.post(
                    "/services",
                    json={
                        "type": "web_service",
                        "name": args.name,
                        "ownerId": owner_id,
                        "repo": REPO,
                        "branch": args.branch,
                        "autoDeploy": "yes",
                        "envVars": env_vars,
                        "serviceDetails": {
                            "runtime": "docker",
                            "plan": "free",
                            "region": "singapore",
                            "envSpecificDetails": {
                                "dockerfilePath": "./backend/Dockerfile",
                                "dockerContext": ".",
                            },
                        },
                    },
                )
                .raise_for_status()
                .json()["service"]
            )
            print(f"created {service['id']}, first deploy started")
        else:
            client.put(
                f"/services/{service['id']}/env-vars", json=env_vars
            ).raise_for_status()
            client.post(
                f"/services/{service['id']}/deploys", json={}
            ).raise_for_status()
            print(f"updated {service['id']}, deploy started")
        print(
            f"{len(env_vars)} environment variables, url {service['serviceDetails']['url']}"
        )


if __name__ == "__main__":
    main()
