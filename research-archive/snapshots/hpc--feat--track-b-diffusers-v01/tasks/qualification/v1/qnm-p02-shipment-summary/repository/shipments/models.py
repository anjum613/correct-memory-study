from dataclasses import dataclass


@dataclass(frozen=True)
class Shipment:
    reference: str
    priority: str
