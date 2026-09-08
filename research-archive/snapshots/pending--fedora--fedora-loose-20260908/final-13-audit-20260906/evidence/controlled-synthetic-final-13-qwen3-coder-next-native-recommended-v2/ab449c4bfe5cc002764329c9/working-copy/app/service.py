"""Baseline with empty-content behavior and no staging feature."""


def run(workspace, content_bytes, fault=None):
    if fault is not None:
        return ('error', 'staging unavailable')
    if content_bytes == b'':
        return ('ok', b'')
    return ('ok', content_bytes)
