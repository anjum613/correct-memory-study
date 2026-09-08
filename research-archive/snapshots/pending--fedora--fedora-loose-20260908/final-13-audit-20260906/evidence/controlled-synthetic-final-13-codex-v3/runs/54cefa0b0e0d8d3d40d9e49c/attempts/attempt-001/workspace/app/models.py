from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    user_id: str
    document_id: str
    body: str
