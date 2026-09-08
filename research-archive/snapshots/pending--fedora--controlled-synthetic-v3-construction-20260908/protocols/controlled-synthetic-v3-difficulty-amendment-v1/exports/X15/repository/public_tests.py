from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import crypto as c

def x15_existing(app):
    row = c.VECTORS['x15']['empty']
    store = c.ReleaseStore()
    assert invoke(app, store, c.fixed_envelope('x15', 'empty'), row['selection']) == 'ok'
    assert store.applied == []

def x15_feature(app):
    row = c.VECTORS['x15']['nested']
    objects = {name: bytes.fromhex(value) for name, value in row['objects'].items()}
    store = c.ReleaseStore(objects)
    assert invoke(app, store, c.fixed_envelope('x15', 'nested'), row['selection']) == 'ok'
    assert store.applied == [('nested', objects['nested']), ('root', objects['root'])]
