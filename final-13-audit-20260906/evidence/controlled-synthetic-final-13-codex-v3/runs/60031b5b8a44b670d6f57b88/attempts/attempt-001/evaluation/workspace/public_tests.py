from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x11_existing(app):
    workspace = r.X11Workspace()
    assert invoke(app, workspace, b'') == ('ok', b'')
    assert workspace.files == {}

def x11_feature(app):
    for payload in (b'staged', b'', b'x' * 64):
        workspace = r.X11Workspace()
        assert invoke(app, workspace, payload) == ('ok', payload)
        assert workspace.files == {}
    for fault in ('create', 'write', 'handoff', 'read'):
        workspace = r.X11Workspace()
        assert invoke(app, workspace, b'staged', fault)[0] == 'error'
        assert workspace.files == {}
