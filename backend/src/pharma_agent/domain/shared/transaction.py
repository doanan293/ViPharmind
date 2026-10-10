"""One database transaction, opaque to the domain and application layers.

Repositories that take a `Transaction` write inside it, so a change and its audit event
commit together or not at all. Infrastructure decides what the handle really is.
"""

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class Transaction(Protocol):
    """Marker for the handle a `TransactionFactory` yields."""


class TransactionFactory(Protocol):
    def begin(self) -> AbstractAsyncContextManager[Transaction]:
        """Commit when the block exits normally, roll back when it raises."""
        ...
