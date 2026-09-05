from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import contracts as k
from fixture_api import runtime as r

def _x26_expected(payload):
    return bytes([len(payload), 0]) + payload + bytes(k.X26_PAYLOAD_LIMIT - len(payload))

def x26_existing(app):
    payload = b'abcdefghijklmn'
    pool = r.X26Scratch(bytes(k.X26_RECORD_WIDTH))
    assert invoke(app, pool, payload) == ('ok', _x26_expected(payload))

def x26_feature(app):
    for size in range(k.X26_PAYLOAD_LIMIT + 1):
        payload = bytes((index % 251 for index in range(size)))
        pool = r.X26Scratch(bytes(k.X26_RECORD_WIDTH))
        assert invoke(app, pool, payload) == ('ok', _x26_expected(payload))
    for invalid in (b'x' * (k.X26_PAYLOAD_LIMIT + 1), 'not-bytes'):
        assert invoke(app, r.X26Scratch(), invalid) == ('invalid', None)
