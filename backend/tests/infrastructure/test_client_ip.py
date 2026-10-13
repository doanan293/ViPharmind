import pytest
from starlette.requests import Request

from pharma_agent.infrastructure.auth.client_ip import client_ip_of


def request(forwarded: str | None, peer: str = "10.0.0.7") -> Request:
    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": (peer, 5000),
            "method": "GET",
            "path": "/",
        }
    )


def test_without_a_trusted_proxy_the_header_is_ignored() -> None:
    assert client_ip_of(request("203.0.113.9"), trusted_hops=0) == "10.0.0.7"


@pytest.mark.parametrize(
    ("header", "hops", "expected"),
    [
        ("203.0.113.9", 1, "203.0.113.9"),
        ("198.51.100.1, 203.0.113.9", 1, "203.0.113.9"),
        ("198.51.100.1, 203.0.113.9", 2, "198.51.100.1"),
    ],
)
def test_the_client_is_counted_from_the_right(
    header: str, hops: int, expected: str
) -> None:
    assert client_ip_of(request(header), trusted_hops=hops) == expected


def test_a_short_or_missing_header_falls_back_to_the_peer() -> None:
    assert client_ip_of(request(None), trusted_hops=1) == "10.0.0.7"
    assert client_ip_of(request("203.0.113.9"), trusted_hops=2) == "10.0.0.7"


def test_no_client_at_all_gives_none() -> None:
    bare = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    assert client_ip_of(bare, trusted_hops=1) is None


def proxied(forwarded: str, secret: str | None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())]
    if secret is not None:
        headers.append((b"x-vipharmind-proxy", secret.encode()))
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": ("10.0.0.7", 5000),
            "method": "GET",
            "path": "/",
        }
    )


def test_our_own_proxy_adds_one_trusted_hop() -> None:
    # Browser → frontend proxy (sets the client) → backend edge (appends the proxy's egress IP).
    header = "198.51.100.1, 76.76.21.9"
    assert (
        client_ip_of(proxied(header, "s3cret"), trusted_hops=1, proxy_secret="s3cret")
        == "198.51.100.1"
    )


def test_a_caller_without_the_secret_cannot_choose_its_ip() -> None:
    # Someone calling the backend directly with a forged header: the edge appends the real IP.
    header = "1.2.3.4, 203.0.113.50"
    for secret in (None, "guess"):
        assert (
            client_ip_of(proxied(header, secret), trusted_hops=1, proxy_secret="s3cret")
            == "203.0.113.50"
        )
