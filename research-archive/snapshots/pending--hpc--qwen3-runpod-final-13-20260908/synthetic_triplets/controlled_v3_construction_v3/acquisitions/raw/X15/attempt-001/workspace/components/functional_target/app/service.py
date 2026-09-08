"""Apply artifact selections authenticated by the fixed publisher."""

import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_PUBLISHER_KEY = bytes.fromhex(
    '03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8'
)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('invalid JSON constant')


def _statement(envelope):
    if type(envelope) not in (tuple, list) or len(envelope) != 2:
        raise ValueError('invalid envelope')
    body, signature = envelope
    if type(body) is not bytes or type(signature) is not bytes:
        raise ValueError('invalid envelope bytes')
    Ed25519PublicKey.from_public_bytes(_PUBLISHER_KEY).verify(signature, body)
    metadata = json.loads(body, object_pairs_hook=_pairs,
                          parse_constant=_invalid_constant)
    canonical = json.dumps(metadata, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True, allow_nan=False).encode('ascii')
    if canonical != body:
        raise ValueError('noncanonical record')
    if type(metadata) is not dict or set(metadata) != {'artifacts', 'release', 'version'}:
        raise ValueError('invalid release')
    if type(metadata['release']) is not str or type(metadata['version']) is not int:
        raise ValueError('invalid release fields')
    return metadata


def _artifacts(metadata):
    artifacts = {}
    pending = [metadata['artifacts']]
    while pending:
        entries = pending.pop()
        if type(entries) is not list:
            raise ValueError('invalid artifact list')
        for entry in entries:
            if type(entry) is not dict or set(entry) != {'name', 'digest', 'children'}:
                raise ValueError('invalid artifact')
            name, digest = entry['name'], entry['digest']
            if type(name) is not str or not name or name in artifacts:
                raise ValueError('ambiguous artifact name')
            if (type(digest) is not str or len(digest) != 64
                    or any(char not in '0123456789abcdef' for char in digest)):
                raise ValueError('invalid artifact digest')
            artifacts[name] = digest
            pending.append(entry['children'])
    return artifacts


def run(release_store, signed_envelope, selection):
    try:
        artifacts = _artifacts(_statement(signed_envelope))
        if type(selection) not in (list, tuple):
            raise ValueError('invalid selection')
        names = []
        seen = set()
        for name in selection:
            if type(name) is not str or name not in artifacts:
                raise ValueError('unknown artifact')
            if name not in seen:
                names.append(name)
                seen.add(name)
        values = []
        for name in names:
            content = release_store.fetch(name)
            if type(content) is not bytes:
                raise ValueError('missing artifact')
            if hashlib.sha256(content).hexdigest() != artifacts[name]:
                raise ValueError('artifact digest mismatch')
            values.append((name, content))
    except Exception:
        return 'invalid'
    release_store.apply(values)
    return 'ok'
