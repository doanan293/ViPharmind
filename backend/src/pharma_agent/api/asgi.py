"""Module-level ASGI app for hosts that import one instead of running `pharma-agent serve`.

Vercel Functions load `app` from here (`[tool.vercel] entrypoint` in pyproject.toml).
"""

from pharma_agent.api.app import create_app

app = create_app()
