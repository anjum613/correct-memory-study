from dataclasses import dataclass


@dataclass(frozen=True)
class CsvRow:
    text: str
