from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x24_existing(app):
    assert invoke(app, r.X24Decisions(), 'read', 'a') == {'one': True, 'two': True}

def x24_feature(app):
    store = r.X24Decisions()
    first = invoke(app, store, 'prepare', ('a', 'one'))
    second = invoke(app, store, 'prepare', ('b', 'two'))
    assert invoke(app, store, 'commit', first) == 'committed'
    assert invoke(app, store, 'commit', second) == 'committed'
    assert store.valid()
