"""SmsSender adapters. A paid provider is plugged in before launch (sub-project 5)."""

import logging

logger = logging.getLogger(__name__)


class LogSmsSender:
    async def send(self, *, to: str, text: str) -> None:
        logger.warning("SMS provider is 'log'; not sent to %s: %s", to, text)
