from __future__ import annotations

class X16Sessions:

    def __init__(self, now=100, lifetime=20):
        self.rows = {}
        self.now = now
        self.lifetime = lifetime
        self.serial = 0

    def fresh(self):
        self.serial += 1
        return ('server-session', self.serial, object())

    def advance(self, amount):
        self.now += amount

    def active(self, identity):
        row = self.rows.get(identity)
        if row is not None and row.get('expires_at', self.now + 1) <= self.now:
            self.rows.pop(identity, None)
            return None
        return row
