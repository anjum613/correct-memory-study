"""Baseline with empty-content behavior and no staging feature."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    return ('error', 'staging unavailable')
