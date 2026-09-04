from dataclasses import dataclass


@dataclass(frozen=True)
class Redirect:
    location: str
