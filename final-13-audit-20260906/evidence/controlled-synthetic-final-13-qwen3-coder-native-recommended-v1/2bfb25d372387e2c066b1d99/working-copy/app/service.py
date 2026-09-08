"""Baseline with empty-content behavior and no staging feature."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    # Create staging area
    identity = workspace.create(['producer', 'consumer'], content_bytes)
    
    # If fault is specified, return error and cleanup
    if fault:
        workspace.remove(identity)
        return ('error', 'staging failed')
    
    # Normal operation
    workspace.permissions(identity, ['consumer'])
    workspace.remove(identity)
    
    return ('ok', content_bytes)
