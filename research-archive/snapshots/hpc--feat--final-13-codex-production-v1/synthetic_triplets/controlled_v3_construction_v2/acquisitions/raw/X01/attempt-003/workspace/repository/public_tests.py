from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x01_existing(app):
    directory = r.X01Directory()
    assert invoke(app, directory, 'absent', b'new') == 'missing'
    assert directory.objects[1]['data'] == b'old' and directory.temporary == {}

def x01_feature(app):
    for payload in (b'', b'replacement', b'x' * 64):
        directory = r.X01Directory()
        assert invoke(app, directory, 'report', payload) == 'updated'
        assert directory.objects[1]['data'] == payload
        assert directory.objects[2]['data'] == b'private-fixture'
        assert directory.temporary == {}
    directory = r.X01Directory()
    assert invoke(app, directory, 'other', b'no') == 'denied'
    for fault in ('fail_stage', 'fail_commit'):
        directory = r.X01Directory()
        setattr(directory, fault, True)
        assert invoke(app, directory, 'report', b'new') == 'error'
        assert directory.objects[1]['data'] == b'old' and directory.temporary == {}
