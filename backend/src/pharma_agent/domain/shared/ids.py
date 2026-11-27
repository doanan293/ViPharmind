from uuid import uuid4


def new_id() -> str:
    """A new random id as 32 hex characters."""
    return uuid4().hex
