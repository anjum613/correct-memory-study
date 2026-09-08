"""Benign public integration fixture: collects normal calls/results only. It is not an implementation of the deployment's execution semantics."""
from __future__ import annotations

class X10Sink:

    def __init__(self):
        self.deliveries = []

    def deliver(self, mode, media_type, filename, payload):
        self.deliveries.append((mode, media_type, filename, bytes(payload)))
