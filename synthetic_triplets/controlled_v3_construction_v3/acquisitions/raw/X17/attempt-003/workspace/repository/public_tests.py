from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x17_existing(app):
    store = r.X17Bundles()
    assert invoke(app, store) == {'left': b'old-L', 'right': b'old-R'}

def x17_feature(app):
    for stop in ('before-left', 'left', 'right', 'before-publish', 'published'):
        store = r.X17Bundles()
        assert invoke(app, store, 'new', b'L', b'R', stop) == 'paused'
        assert invoke(app, store, 'new', b'L', b'R') == 'complete'
        assert invoke(app, store) == {'left': b'L', 'right': b'R'}
