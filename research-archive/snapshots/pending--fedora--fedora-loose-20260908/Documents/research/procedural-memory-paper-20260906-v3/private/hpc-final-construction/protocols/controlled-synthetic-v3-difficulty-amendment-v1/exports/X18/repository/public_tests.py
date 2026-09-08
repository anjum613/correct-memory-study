from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import crypto as c

def x18_existing(app):
    store = c.Installer(2, b'current')
    assert invoke(app, store, c.fixed_envelope('x18', 'current')) == 'current'
    assert store.committed == (2, b'current')

def x18_feature(app):
    store = c.Installer(2, b'current')
    assert invoke(app, store, None) == 'offline'
    assert invoke(app, store, c.fixed_envelope('x18', 'newer'), 'staged') == 'interrupted'
    assert store.committed == (2, b'current')
    assert invoke(app, store, None) == 'installed'
    assert store.committed == (3, b'new')
