"""The caller's IP, for per-IP limits and the session list.

Behind a reverse proxy the TCP peer is the proxy, so every user would share one IP.
`X-Forwarded-For` names the real client, but only the entries added by proxies we run can
be trusted: a client can prepend anything. Counting `trusted_hops` entries from the right
skips whatever the client wrote.
"""

from starlette.requests import Request


def client_ip_of(request: Request, *, trusted_hops: int) -> str | None:
    peer = None if request.client is None else request.client.host
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
    return client_ip_of(request, trusted_hops=hops if isinstance(hops, int) else 0)
