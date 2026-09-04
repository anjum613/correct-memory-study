from dataclasses import dataclass


@dataclass(frozen=True)
class Reservation:
    name: str
    owner: str
