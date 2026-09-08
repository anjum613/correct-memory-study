from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x14_existing(app):
    context = r.X14Context()
    assert invoke(app, context, []) == []

def x14_feature(app):
    context = r.X14Context()
    callbacks = [r.X14Callback(('notify',), 'first'), r.X14Callback(('observe',), 'status'), r.X14Callback(('notify',), 'ignored', raises=True), r.X14Callback(('notify',), 'second')]
    assert invoke(app, context, callbacks) == ['ok', 'ok', 'callback-error', 'ok']
    assert context.notifications == ['first', 'second'] and context.observations == ['status']
    assert callbacks[0].invoke_captured(('notify',), 'after-return') == 'ok'
    assert context.notifications[-1] == 'after-return'
