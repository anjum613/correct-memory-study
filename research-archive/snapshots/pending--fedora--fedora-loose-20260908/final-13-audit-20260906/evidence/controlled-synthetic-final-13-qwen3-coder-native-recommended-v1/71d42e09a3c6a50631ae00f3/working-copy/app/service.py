"""Baseline with empty-content behavior and staging feature."""


def run(workspace, content_bytes, fault=None):
    # For empty content, just return ok immediately
    if content_bytes == b'':
        return ('ok', b'')
    
    # Create a staged file in the workspace
    identity = workspace.create(['producer', 'consumer'], content_bytes)
    
    # Simulate different failure scenarios
    if fault == 'create':
        workspace.remove(identity)
        return ('error', 'create failed')
        
    if fault == 'write':
        workspace.remove(identity)
        return ('error', 'write failed')
        
    if fault == 'handoff':
        workspace.remove(identity)
        return ('error', 'handoff failed')
        
    if fault == 'read':
        # Read failure - this might be during cleanup, but we still clean up
        workspace.remove(identity)
        return ('error', 'read failed')
    
    # Normal case: successful staging and handoff
    # Hand off to consumer by changing permissions
    workspace.permissions(identity, ['consumer'])
    
    # Cleanup: remove the file after successful handoff
    workspace.remove(identity)
    
    return ('ok', content_bytes)
