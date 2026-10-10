"""Email content shared by every feature: the locale and a plain HTML layout."""

from dataclasses import dataclass
from html import escape
from typing import Literal

Locale = Literal["vi", "en"]


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


def locale_from_accept_language(header: str | None) -> Locale:
    first = (header or "").split(",")[0].strip().lower()
    return "en" if first.startswith("en") else "vi"


def html_message(
    subject: str,
    body: str,
    *,
    highlight: str | None = None,
    link: tuple[str, str] | None = None,
) -> str:
    """`highlight` is shown large (a code); `link` is (label, url) shown as a button."""
    parts = [f"<h2>{escape(subject)}</h2>"]
    if highlight is not None:
        parts.append(
            '<p style="font-size:32px;font-weight:bold;letter-spacing:4px">'
            f"{escape(highlight)}</p>"
        )
    parts.append(f"<p>{escape(body)}</p>")
    if link is not None:
        label, url = link
        parts.append(
            f'<p><a href="{escape(url, quote=True)}" style="display:inline-block;'
            "padding:10px 16px;background:#0f766e;color:#fff;border-radius:6px;"
            f'text-decoration:none">{escape(label)}</a></p>'
        )
    return (
        '<div style="font-family:sans-serif;color:#1f2937">' + "".join(parts) + "</div>"
    )
