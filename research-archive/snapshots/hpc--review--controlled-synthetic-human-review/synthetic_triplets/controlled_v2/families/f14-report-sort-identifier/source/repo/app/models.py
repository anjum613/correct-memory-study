from dataclasses import dataclass


@dataclass(frozen=True)
class ReportRow:
    report_id: int
    name: str
