from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x09_existing(app):
    store = r.X09Store()
    result = invoke(app, store, 'legacy', {'delta': 1})
    assert isinstance(result, tuple) and result[:2] == ('ack', 'legacy')

def x09_feature(app):
    store = r.X09Store()
    first = invoke(app, store, 'one', {'delta': 2})
    retry = invoke(app, store, 'one', {'delta': 2})
    second = invoke(app, store, 'two', {'delta': 2})
    assert first == retry and second != first
