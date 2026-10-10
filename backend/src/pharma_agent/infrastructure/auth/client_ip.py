"""The caller's IP, for per-IP limits and the session list.

Behind a reverse proxy the TCP peer is the proxy, so every user would share one IP.
`X-Forwarded-For` names the real client, but only the entries added by proxies we run can
be trusted: a client can prepend anything. Counting `trusted_hops` entries from the right
skips whatever the client wrote.

Our own same-origin proxy (the frontend's `/api/*` route on Vercel) is one more hop, but only
for requests that prove they came through it with the shared `X-Vipharmind-Proxy` secret;
anyone calling the backend directly keeps the configured count and cannot pick an IP.
"""

import hmac

from starlette.requests import Request

PROXY_HEADER = "x-vipharmind-proxy"


def _from_our_proxy(request: Request, proxy_secret: str | None) -> bool:
    sent = request.headers.get(PROXY_HEADER)
    return (
        proxy_secret is not None
        and sent is not None
        and hmac.compare_digest(sent.encode(), proxy_secret.encode())
    )


def client_ip_of(
    request: Request, *, trusted_hops: int, proxy_secret: str | None = None
) -> str | None:
    peer = None if request.client is None else request.client.host
    if trusted_hops > 0 and _from_our_proxy(request, proxy_secret):
        trusted_hops += 1
    if trusted_hops <= 0:
        return peer
    entries = [
        entry.strip()
        for entry in request.headers.get("x-forwarded-for", "").split(",")
        if entry.strip()
    ]
    if len(entries) < trusted_hops:
        return peer
    return entries[-trusted_hops]


def request_client_ip(request: Request) -> str | None:
    """`client_ip_of` with the hop count the app was configured with."""
    hops = getattr(request.app.state, "trusted_proxy_hops", 0)
    secret = getattr(request.app.state, "proxy_secret", None)
    return client_ip_of(
        request,
        trusted_hops=hops if isinstance(hops, int) else 0,
        proxy_secret=secret if isinstance(secret, str) and secret else None,
    )
