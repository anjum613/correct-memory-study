from __future__ import annotations

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fixture_api.public_harness import invoke
from fixture_api import contracts as k
from fixture_api import runtime as r

def _decrypt_x05(packet):
    return AESGCM(bytes(range(32))).decrypt(packet[:k.X05_NONCE_BYTES], packet[k.X05_NONCE_BYTES:], k.X05_AAD)

def x05_existing(app):
    system = r.X05System()
    for payload in (b'', b'one', b'x' * 32):
        packet = invoke(app, system, 'one', payload)
        assert isinstance(packet, bytes) and _decrypt_x05(packet) == payload
    system.restart('one')
    packet = invoke(app, system, 'one', b'after-restart')
    assert _decrypt_x05(packet) == b'after-restart'

def x05_feature(app):
    system = r.X05System()
    for worker, payload in (('one', b'a'), ('two', b'b'), ('three', b'c')):
        packet = invoke(app, system, worker, payload)
        assert isinstance(packet, bytes) and _decrypt_x05(packet) == payload
    system = r.X05System()
    for _ in range(k.X05_COUNTER_LIMIT):
        assert isinstance(invoke(app, system, 'one', b'fill'), bytes)
    assert invoke(app, system, 'one', b'over') == 'exhausted'
