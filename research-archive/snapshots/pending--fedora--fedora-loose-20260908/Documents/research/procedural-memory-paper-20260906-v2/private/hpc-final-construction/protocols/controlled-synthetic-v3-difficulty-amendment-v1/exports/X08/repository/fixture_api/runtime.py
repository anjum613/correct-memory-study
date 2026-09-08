from __future__ import annotations

class X08Sink:

    def __init__(self):
        self.entries = []
        self.work = 0
        self.peak_buffered = 0
        self.cleanup_count = 0

    def publish(self, entries):
        self.entries.extend(((name, bytes(data)) for name, data in entries))

    def cleanup(self):
        self.cleanup_count += 1
