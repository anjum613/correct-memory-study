from __future__ import annotations

import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
VECTORS = json.loads(Path(__file__).with_name('public_vectors.json').read_text())

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')

def exact_object(data):

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    if type(data) is not bytes:
        raise ValueError('record bytes required')
    value = json.loads(data, object_pairs_hook=pairs)
    if canonical(value) != data:
        raise ValueError('noncanonical record')
    return value

def publisher_public_key():
    return ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(VECTORS['ed25519_public_hex']))

def fixed_envelope(section, name):
    row = VECTORS[section][name]
    return (bytes.fromhex(row['body_hex']), bytes.fromhex(row['signature_hex']))

class Installer:

    def __init__(self, version=2, payload=b'current'):
        self.committed = (version, payload)
        self.pending = None
        self.observations = [self.committed]

    def stage(self, envelope):
        self.pending = envelope
        self.observations.append(self.committed)

    def commit(self, version, payload):
        self.committed = (version, payload)
        self.observations.append(self.committed)
        self.pending = None
