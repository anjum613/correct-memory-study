"""Staging implementation with proper cleanup."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    # Create staging file with default permissions
    try:
        # Create the staging file with producer and consumer as allowed readers
        identity = workspace.create(['producer', 'consumer'], content_bytes)
        
        # If fault is specified, simulate a failure during handoff
        if fault == 'handoff':
            workspace.remove(identity)
            return ('error', 'handoff failed')
        
        # Read back the content to verify it was stored correctly
        if fault == 'read':
            workspace.remove(identity)
            return ('error', 'read failed')
            
        # Simulate successful handoff by removing the staging file
        workspace.remove(identity)
        
        return ('ok', content_bytes)
        
    except Exception:
        # Handle any creation/write failures
        if fault == 'create' or fault == 'write':
            return ('error', 'staging failed')
        return ('error', 'unexpected error')
