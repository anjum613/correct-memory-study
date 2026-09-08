from dataclasses import dataclass


@dataclass(frozen=True)
class Badge:
    html: str
