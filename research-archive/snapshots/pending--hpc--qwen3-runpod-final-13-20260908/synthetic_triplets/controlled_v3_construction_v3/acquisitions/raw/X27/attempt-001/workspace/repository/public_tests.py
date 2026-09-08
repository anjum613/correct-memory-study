from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x27_existing(app):
    service = r.X27Pages({0: ([], None)})
    decision = invoke(app, service, 'item')
    assert decision.effect == 'allow' and service.grants == ['item']

def x27_feature(app):
    service = r.X27Pages({0: (['other'], 1), 1: ([], 2), 2: (['unrelated'], None)})
    decision = invoke(app, service, 'item')
    assert decision.effect == 'allow' and service.grants == ['item']
