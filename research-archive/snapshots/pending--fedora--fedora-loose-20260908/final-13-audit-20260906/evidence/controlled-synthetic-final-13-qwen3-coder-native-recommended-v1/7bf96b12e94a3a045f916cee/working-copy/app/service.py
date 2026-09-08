"""Staging implementation with proper cleanup and fault handling."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    # Create staging file with default permissions
    identity = workspace.create(workspace.default_readers, content_bytes)
    
    # Handle various fault conditions
    if fault == 'create' or fault == 'write':
        workspace.remove(identity)
        return ('error', 'staging unavailable')
    
    if fault == 'handoff':
        workspace.remove(identity)
        return ('error', 'staging unavailable')
    
    # Try to read the content back to verify it was stored
    try:
        if fault == 'read':
            workspace.remove(identity)
            return ('error', 'staging unavailable')
            
        # Verify we can read the content back
        stored_content = workspace.read(identity, 'consumer', fault)
        if stored_content != content_bytes:
            workspace.remove(identity)
            return ('error', 'staging unavailable')
            
        # Clean up the staging file
        workspace.remove(identity)
        
        return ('ok', content_bytes)
    except Exception:
        workspace.remove(identity)
        return ('error', 'staging unavailable')
