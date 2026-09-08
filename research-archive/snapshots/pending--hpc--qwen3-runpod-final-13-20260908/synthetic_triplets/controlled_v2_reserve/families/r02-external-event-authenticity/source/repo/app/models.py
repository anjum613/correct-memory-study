from dataclasses import dataclass


@dataclass(frozen=True)
class EventReceipt:
    body: str
    accepted: bool
