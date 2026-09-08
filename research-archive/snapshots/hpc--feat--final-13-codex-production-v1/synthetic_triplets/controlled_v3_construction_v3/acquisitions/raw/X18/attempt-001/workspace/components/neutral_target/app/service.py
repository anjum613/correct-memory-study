"""Authenticated online release installation without cache recovery."""

import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_PUBLIC_KEY = bytes.fromhex(
    '03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8'
)
_MAX_VERSION = 2 ** 63 - 1


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def _release(envelope):
    if type(envelope) not in (tuple, list) or len(envelope) != 2:
        raise ValueError('invalid envelope')
    body, signature = envelope
    if type(body) is not bytes or type(signature) is not bytes:
        raise ValueError('invalid envelope bytes')
    Ed25519PublicKey.from_public_bytes(_PUBLIC_KEY).verify(signature, body)
    record = json.loads(body, object_pairs_hook=_pairs)
    if type(record) is not dict or set(record) != {'version', 'payload_hex'}:
        raise ValueError('invalid release fields')
    canonical = json.dumps(
        record, sort_keys=True, separators=(',', ':'), ensure_ascii=True
    ).encode('ascii')
    if canonical != body:
        raise ValueError('noncanonical release')
    version = record['version']
    if type(version) is not int or not 0 <= version <= _MAX_VERSION:
        raise ValueError('invalid version')
    encoded = record['payload_hex']
    if type(encoded) is not str:
        raise ValueError('invalid payload')
    payload = bytes.fromhex(encoded)
    if payload.hex() != encoded:
        raise ValueError('noncanonical payload')
    return version, payload


def run(installer, signed_envelope=None, interruption=None):
    if signed_envelope is None:
        return 'unavailable'
    try:
        version, payload = _release(signed_envelope)
    except Exception:
        return 'rejected'
    if version == installer.committed[0]:
        return 'current'
    installer.commit(version, payload)
    return 'installed'
