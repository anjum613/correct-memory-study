from __future__ import annotations

from . import contracts as k

class X26Scratch:

    def __init__(self, previous=b'previous'):
        pattern = previous or b'\xff'
        self.previous = bytes((pattern * k.X26_RECORD_WIDTH)[:k.X26_RECORD_WIDTH])
        self.frames = []
        self.partial_frames = []

    def take(self):
        return bytearray(self.previous)

    def transmit(self, block, fail_after=None):
        value = bytes(block)
        if fail_after is not None:
            if not 0 <= fail_after <= len(value):
                raise ValueError('invalid partial boundary')
            self.partial_frames.append(value[:fail_after])
            return ('error', value[:fail_after])
        self.frames.append(value)
        return ('ok', value)
