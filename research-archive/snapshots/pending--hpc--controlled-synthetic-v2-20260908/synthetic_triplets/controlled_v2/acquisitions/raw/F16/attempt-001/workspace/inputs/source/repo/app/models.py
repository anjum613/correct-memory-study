from dataclasses import dataclass


@dataclass(frozen=True)
class Parent:
    parent_id: str
    child_ids: tuple[str, ...]


@dataclass(frozen=True)
class Child:
    child_id: str
    parent_id: str
    body: str
