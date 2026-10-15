from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerLayout:
    visible_devices: str


# One replica of the model on each of the two T4s.
SERVER_LAYOUTS = (ServerLayout("0"), ServerLayout("1"))
