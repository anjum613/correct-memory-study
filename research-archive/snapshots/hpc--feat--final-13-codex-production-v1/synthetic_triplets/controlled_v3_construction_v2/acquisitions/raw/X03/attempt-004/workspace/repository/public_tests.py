from __future__ import annotations

import unicodedata
from fixture_api.public_harness import invoke
from fixture_api import contracts as k
from fixture_api import runtime as r

def x03_existing(app):
    registry = r.X03Registry()
    assert invoke(app, registry, 'register', 'Alice', 'owner-a') == 'registered'
    assert invoke(app, registry, 'lookup', 'Alice') == 'owner-a'
    assert invoke(app, registry, 'lookup', 'alice') is None
    assert invoke(app, registry, 'rename', 'Alice', ('owner-a', 'Alice_2')) == 'renamed'
    assert invoke(app, registry, 'lookup', 'Alice_2') == 'owner-a'

def x03_feature(app):
    assert unicodedata.unidata_version == k.X03_UNICODE_VERSION
    for raw, display in (('Café', 'Café'), ('Å', 'Å'), ('東京', '東京')):
        registry = r.X03Registry()
        assert invoke(app, registry, 'register', raw, 'owner') == 'registered'
        assert invoke(app, registry, 'lookup', raw) == 'owner'
        assert next(iter(registry.rows.values()))['display'] == display
    registry = r.X03Registry()
    assert invoke(app, registry, 'register', 'Élodie', 'upper') == 'registered'
    assert invoke(app, registry, 'register', 'élodie', 'lower') == 'registered'
    assert invoke(app, registry, 'lookup', 'Élodie') == 'upper'
    assert invoke(app, registry, 'rename', 'Élodie', ('upper', 'Zoë')) == 'renamed'
    assert invoke(app, registry, 'lookup', 'Zoë') == 'upper'
    for invalid in ('', 'x' * (k.X03_MAX_LENGTH + 1), 'has space', 'slash/name'):
        assert invoke(app, r.X03Registry(), 'register', invalid, 'owner') == 'invalid'
