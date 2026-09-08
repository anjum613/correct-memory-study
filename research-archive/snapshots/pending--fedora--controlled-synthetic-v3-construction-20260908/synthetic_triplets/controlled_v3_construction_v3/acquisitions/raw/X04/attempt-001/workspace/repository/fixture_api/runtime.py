from __future__ import annotations

import json

class X04Sink:

    def __init__(self, fail=False):
        self.frames = []
        self.fail = fail

    def emit(self, data):
        if self.fail:
            raise OSError('controlled sink failure')
        self.frames.append(bytes(data))

def _x04_encode(rows, format_name):
    if format_name == 'framed':
        output = bytearray()
        for identity, payload in rows:
            name = identity.encode('ascii')
            output += len(name).to_bytes(1, 'big') + name
            output += len(payload).to_bytes(2, 'big') + payload
        return bytes(output)
    if format_name == 'json-lines':
        return b''.join((json.dumps({'id': identity, 'payload_hex': payload.hex()}, sort_keys=True, separators=(',', ':')).encode('ascii') + b'\n' for identity, payload in rows))
    raise ValueError('unsupported format')
