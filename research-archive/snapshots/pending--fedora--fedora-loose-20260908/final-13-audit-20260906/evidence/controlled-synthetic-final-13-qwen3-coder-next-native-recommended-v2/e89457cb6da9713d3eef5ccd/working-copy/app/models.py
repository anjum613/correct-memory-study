from dataclasses import dataclass


@dataclass(frozen=True)
class ExportReceipt:
    path: str
