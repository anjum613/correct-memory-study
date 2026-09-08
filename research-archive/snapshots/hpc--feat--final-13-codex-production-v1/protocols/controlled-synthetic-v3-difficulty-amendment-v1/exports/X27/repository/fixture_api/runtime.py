from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class X27Decision:
    effect: str
    explanation: str
    pages: int

class X27Pages:
    ERROR = object()

    def __init__(self, pages):
        self.pages = dict(pages)
        self.calls = []
        self.grants = []

    def fetch(self, cursor):
        self.calls.append(cursor)
        return self.pages.get(cursor, self.ERROR)
