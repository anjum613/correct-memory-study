from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x10_existing(app):
    sink = r.X10Sink()
    payload = b'opaque bytes'
    assert invoke(app, sink, 'application/octet-stream', 'file.bin', payload) == 'download'
    assert sink.deliveries == [('download', 'application/octet-stream', 'file.bin', payload)]

def x10_feature(app):
    cases = (('text/plain', 'note.txt', b'TXT\x00ordinary\ntext'), ('image/x-local-pixels', 'image.pix', b'PIX\x00\x01\x02' + bytes(range(6))))
    for claim, filename, payload in cases:
        sink = r.X10Sink()
        assert invoke(app, sink, claim, filename, payload) == 'inline'
        assert sink.deliveries == [('inline', claim, filename, payload)]
    sink = r.X10Sink()
    payload = b'unknown-content'
    assert invoke(app, sink, 'application/x-unknown', 'unknown.bin', payload) == 'download'
    assert sink.deliveries[-1][-1] == payload
