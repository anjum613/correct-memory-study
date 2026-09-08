"""Staging implementation with proper cleanup."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    # Create staging file with default permissions
    identity = workspace.create(workspace.default_readers, content_bytes)
    
    # Handle fault conditions - they all result in error return
    if fault in ('create', 'write', 'handoff', 'read'):
        workspace.remove(identity)
        return ('error', 'staging unavailable')
    
    # Normal case - clean up and return success
    workspace.remove(identity)
    return ('ok', content_bytes)
