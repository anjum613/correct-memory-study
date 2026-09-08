from __future__ import annotations
from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x28_existing(app):
    store = r.X28Membership(['member'])
    assert invoke(app, store, 'check', 'member') is True
    assert invoke(app, store, 'remove', 'member') is True
    assert invoke(app, store, 'check', 'member') is False
    assert invoke(app, store, 'add', 'other') is True
    assert invoke(app, store, 'check', 'other') is True

def x28_feature(app):
    store = r.X28Membership([], approximate=True)
    assert invoke(app, store, 'check', 'ordinary') is False
    assert store.page_reads == 0
    assert invoke(app, store, 'add', 'ordinary') is True
    assert invoke(app, store, 'check', 'ordinary') is True
    assert invoke(app, store, 'remove', 'ordinary') is True
    assert invoke(app, store, 'check', 'ordinary') is False
