from dataclasses import dataclass


@dataclass(frozen=True)
class Download:
    filename: str
