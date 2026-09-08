from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import contracts as k
from fixture_api import runtime as r

def x08_existing(app):
    sink = r.X08Sink()
    assert invoke(app, [('empty', 0, [])], sink) == 'ok'
    assert sink.entries == [('empty', b'')]

def x08_feature(app):
    cases = [[('first', 3, [(3, 65)]), ('second', 2, [(1, 66), (1, 67)])], [('maximum', k.X08_ENTRY_LIMIT, [(k.X08_ENTRY_LIMIT, 88)]), ('remainder', k.X08_TOTAL_LIMIT - k.X08_ENTRY_LIMIT, [(k.X08_TOTAL_LIMIT - k.X08_ENTRY_LIMIT, 89)])], [(f'e{index}', 0, []) for index in range(k.X08_COUNT_LIMIT)]]
    for entries in cases:
        sink = r.X08Sink()
        assert invoke(app, entries, sink) == 'ok'
        assert [name for name, _ in sink.entries] == [entry[0] for entry in entries]
        assert [data for _, data in sink.entries] == [b''.join((bytes([byte]) * count for count, byte in entry[2])) for entry in entries]
