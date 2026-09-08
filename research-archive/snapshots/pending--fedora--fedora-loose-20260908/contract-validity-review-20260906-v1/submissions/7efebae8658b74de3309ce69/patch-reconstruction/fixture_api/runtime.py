"""Local paged membership storage. Reads return records, not authorization answers."""
from __future__ import annotations

import hashlib


class X28Membership:
    def __init__(self, members=(), approximate=False):
        self.pages = {}
        self.approximate = approximate
        self.grants = []
        self.page_reads = 0
        self.fail_read = False
        for member in members:
            self.insert(member)

    @staticmethod
    def bucket(item):
        return hashlib.sha256(item.encode("ascii")).digest()[0] % 16

    @staticmethod
    def page_for(item):
        hash(item)
        try:
            return X28Membership.bucket(item)
        except (AttributeError, UnicodeEncodeError):
            # Storage retains keys outside the prefilter's byte alphabet too.
            # This does not alter the prefilter's original encoding semantics.
            return -1

    def insert(self, item):
        page = self.page_for(item)
        self.pages.setdefault(page, set()).add(item)

    def remove(self, item):
        page = self.page_for(item)
        self.pages.get(page, set()).discard(item)
        if page in self.pages and not self.pages[page]:
            del self.pages[page]

    def preliminary(self, item):
        if not self.approximate:
            hash(item)
            return any(item in page for page in self.pages.values())
        bits = 0
        for page in self.pages.values():
            for member in page:
                bits |= 1 << self.bucket(member)
        return bool(bits & (1 << self.bucket(item)))

    def read_page(self, page):
        self.page_reads += 1
        if self.fail_read:
            raise OSError("controlled storage read failure")
        return tuple(self.pages.get(page, ()))
