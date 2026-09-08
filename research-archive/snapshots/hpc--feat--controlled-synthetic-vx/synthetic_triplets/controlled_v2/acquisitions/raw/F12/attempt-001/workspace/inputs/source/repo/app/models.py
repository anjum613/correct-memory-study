from dataclasses import dataclass
from enum import Enum


class Mode(Enum):
    FAST = "fast"
    QUALITY = "quality"


@dataclass(frozen=True)
class Job:
    mode: Mode
    path: str


@dataclass(frozen=True)
class Conversion:
    source: str
    ok: bool
