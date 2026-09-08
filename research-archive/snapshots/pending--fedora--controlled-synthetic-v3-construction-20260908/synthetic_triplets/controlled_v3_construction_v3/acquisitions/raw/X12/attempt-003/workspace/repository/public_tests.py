from __future__ import annotations
from fixture_api.public_harness import invoke
from fixture_api import runtime as r
X12_PARENT = {'LOCALE': 'C', 'DATA': 'default', 'TUNING': 'normal', 'REQUIRED': 'fixed'}

def x12_existing(app):
    child = r.X12Child()
    result = invoke(app, child, X12_PARENT, {})
    assert result == r.X12Result(0, ('C', 'default', 'normal', 'fixed'))

def x12_feature(app):
    overlays = ({'LOCALE': 'fr'}, {'DATA': 'secondary', 'TUNING': 'small'}, {'LOCALE': 'de', 'DATA': 'archive', 'TUNING': 'large'})
    for overlay in overlays:
        child = r.X12Child(exit_code=7)
        result = invoke(app, child, X12_PARENT, overlay)
        expected = tuple((overlay.get(name, X12_PARENT[name]) for name in ('LOCALE', 'DATA', 'TUNING', 'REQUIRED')))
        assert result == r.X12Result(7, expected)
