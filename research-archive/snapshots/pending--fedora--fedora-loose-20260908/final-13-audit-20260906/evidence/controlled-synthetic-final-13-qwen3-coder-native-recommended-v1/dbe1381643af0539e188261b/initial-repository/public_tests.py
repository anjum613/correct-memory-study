from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x20_existing(app):
    service = r.X20Service()
    assert invoke(app, service, 'reader', [('mode', 'read'), ('tag', 'one')]) == {'mode': 'read', 'tags': ['one']}

def x20_feature(app):
    service = r.X20Service()
    result = invoke(app, service, 'reader', [('mode', 'read'), ('tag', 'one'), ('tag', 'two'), ('tag', 'one')])
    assert result == {'mode': 'read', 'tags': ['one', 'two', 'one']}
    service = r.X20Service()
    assert invoke(app, service, 'writer', [('mode', 'write'), ('tag', 'ordered')]) == {'mode': 'write', 'tags': ['ordered']}
    assert service.writes == ['local-write']
