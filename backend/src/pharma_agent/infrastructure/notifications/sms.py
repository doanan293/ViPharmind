"""SmsSender adapters. A paid provider is plugged in before launch (sub-project 5)."""

import logging

logger = logging.getLogger(__name__)


class LogSmsSender:
    """SmsSender that only logs the message until a paid provider is plugged in."""

    async def send(self, *, to: str, text: str) -> None:
        """Log the recipient and text instead of sending."""
        logger.warning("SMS provider is 'log'; not sent to %s: %s", to, text)
