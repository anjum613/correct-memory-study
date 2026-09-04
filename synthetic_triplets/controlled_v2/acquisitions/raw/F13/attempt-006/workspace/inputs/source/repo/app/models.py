from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    template: str
    body: str
