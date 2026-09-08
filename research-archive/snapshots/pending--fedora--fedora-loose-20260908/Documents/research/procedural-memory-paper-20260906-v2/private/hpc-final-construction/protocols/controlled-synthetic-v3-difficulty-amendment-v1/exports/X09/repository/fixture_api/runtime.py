from __future__ import annotations

class X09Store:

    def __init__(self):
        self.effects = []
        self.receipts = {}
        self.before_commit = None
