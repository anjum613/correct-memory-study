"""Baseline with empty-content behavior and no staging feature."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    # Create a staged file in the workspace
    identity = workspace.create(['producer', 'consumer'], content_bytes)
    
    # Handle potential faults during staging
    if fault == 'create':
        workspace.remove(identity)
        return ('error', 'staging unavailable')
    
    # Simulate handoff to consumer
    if fault == 'handoff':
        workspace.remove(identity)
        return ('error', 'staging unavailable')
    
    # Handle write fault
    if fault == 'write':
        workspace.remove(identity)
        return ('error', 'staging unavailable')
        
    # Handle read fault  
    if fault == 'read':
        workspace.remove(identity)
        return ('error', 'staging unavailable')
        
    # If we get here, staging succeeded
    # The content should be accessible to consumer
    try:
        content = workspace.read(identity, 'consumer')
        if content != content_bytes:
            workspace.remove(identity)
            return ('error', 'staging unavailable')
    except OSError:
        workspace.remove(identity)
        return ('error', 'staging unavailable')
        
    # Success case - clean up the file since we've verified it worked
    workspace.remove(identity)
    return ('ok', content_bytes)
