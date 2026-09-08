from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractionSummary:
    files: int
    expanded_bytes: int
