from __future__ import annotations

from fixture_api.public_harness import invoke

def x21_existing(app):
    effects = []
    result = invoke(app, [('allow-item', 'allow', 'item')], 'item', effects)
    assert result.effect == 'allow' and effects == ['item']

def x21_feature(app):
    effects = []
    result = invoke(app, [('allow-item', 'allow', 'item'), ('allow-all', 'allow', '*')], 'item', effects)
    assert result.effect == 'allow' and effects == ['item']
    effects = []
    result = invoke(app, [('other', 'allow', 'other')], 'item', effects)
    assert result.effect == 'deny' and effects == []
