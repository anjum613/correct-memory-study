from __future__ import annotations

import hashlib

class X28Membership:

    def __init__(self, members=(), approximate=False):
        self.members = set(members)
        self.approximate = approximate
        self.grants = []
        self.exact_reads = 0
        self.fail_exact = False

    @staticmethod
    def bucket(item):
        return hashlib.sha256(item.encode('ascii')).digest()[0] % 16

    def preliminary(self, item):
        if not self.approximate:
            return item in self.members
        bits = 0
        for member in self.members:
            bits |= 1 << self.bucket(member)
        return bool(bits & 1 << self.bucket(item))

    def exact(self, item):
        self.exact_reads += 1
        if self.fail_exact:
            raise OSError('controlled authoritative-store failure')
        return item in self.members

def _x28_update(store, operation, item):
    if operation == 'add':
        store.members.add(item)
        return True
    if operation == 'remove':
        store.members.discard(item)
        return True
    return None
