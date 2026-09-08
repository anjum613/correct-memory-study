from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x23_existing(app):
    kernel = r.X23Kernel()
    kernel.failure = 'primary'
    assert invoke(app, kernel) is None
    assert kernel.executions == []

def x23_feature(app):
    for intended in (('readers',), ('readers', 'analysts'), ()):
        kernel = r.X23Kernel(inherited=intended, intended=intended)
        assert invoke(app, kernel) == b'job'
        assert kernel.executions == [('worker', 'work', frozenset(intended))]
