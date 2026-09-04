from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    stored: int
