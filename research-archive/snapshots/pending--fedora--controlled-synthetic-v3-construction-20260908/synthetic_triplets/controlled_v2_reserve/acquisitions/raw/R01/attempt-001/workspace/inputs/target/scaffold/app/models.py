from dataclasses import dataclass


@dataclass(frozen=True)
class AuditRecord:
    text: str
