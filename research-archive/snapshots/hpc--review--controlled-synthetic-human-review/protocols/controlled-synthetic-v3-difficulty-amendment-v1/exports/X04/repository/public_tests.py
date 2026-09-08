from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import contracts as k
from fixture_api import runtime as r

def _store(*rows):
    return {identity: {'owner': owner, 'payload': payload} for identity, owner, payload in rows}

def x04_existing(app):
    store = _store(('a', 'one', b'first'))
    for format_name in k.X04_FORMATS:
        sink = r.X04Sink()
        assert invoke(app, store, 'one', ['a'], format_name, sink) == 'ok'
        assert sink.frames == [r._x04_encode([('a', b'first')], format_name)]
    sink = r.X04Sink()
    assert invoke(app, store, 'one', [], 'framed', sink) == 'ok'
    assert sink.frames == [b'']

def x04_feature(app):
    store = _store(('a', 'one', b'first'), ('b', 'one', b'second'), ('c', 'one', b'third'))
    selected = ['b', 'a', 'b', 'c']
    expected = [('b', b'second'), ('a', b'first'), ('c', b'third')]
    for format_name in k.X04_FORMATS:
        sink = r.X04Sink()
        assert invoke(app, store, 'one', selected, format_name, sink) == 'ok'
        assert sink.frames == [r._x04_encode(expected, format_name)]
    sink = r.X04Sink(fail=True)
    assert invoke(app, store, 'one', ['a', 'b'], 'framed', sink) == 'error'
    assert sink.frames == []
