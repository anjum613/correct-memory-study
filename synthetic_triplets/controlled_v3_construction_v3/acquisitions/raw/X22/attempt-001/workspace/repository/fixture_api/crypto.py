from __future__ import annotations

import json
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
VECTORS = json.loads(Path(__file__).with_name('public_vectors.json').read_text())

def suite_padding(suite):
    if suite == 'PS256':
        return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
    if suite == 'RS256':
        return padding.PKCS1v15()
    raise ValueError('unsupported suite')

def x22_body(version, suite, payload):
    return b'X22-message-v' + str(version).encode('ascii') + b'\x00' + suite.encode('ascii') + b'\x00' + len(payload).to_bytes(4, 'big') + payload

class KeySlot:

    def __init__(self, key, key_class):
        self.key = key
        self.key_class = key_class

def rsa_slot(bits, key_class):
    values = VECTORS['rsa_public'][str(bits)]
    public = rsa.RSAPublicNumbers(int(values['e']), int(values['n'])).public_key()
    return KeySlot(public, key_class)

def fixed_x22_fields(bits, key_class, suite, version, payload_id):
    match = next((row for row in VECTORS['x22'] if row == {**row, 'bits': bits, 'suite': suite, 'version': version, 'payload_id': payload_id}))
    payload = bytes.fromhex(VECTORS['payloads'][payload_id])
    return (rsa_slot(bits, key_class), [('version', version), ('suite', suite), ('payload', payload), ('signature', bytes.fromhex(match['signature_hex']))])
