from __future__ import annotations

class X10Sink:

    def __init__(self):
        self.deliveries = []
        self.active_effects = []

    def deliver(self, mode, media_type, filename, payload):
        self.deliveries.append((mode, media_type, filename, bytes(payload)))
        if mode == 'inline' and payload.startswith(b'ACT\x00'):
            self.active_effects.append(payload[4:])
