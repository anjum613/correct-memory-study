"""Staging implementation with proper cleanup and fault handling."""

def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    try:
        # Create staging file with default permissions
        staging_id = workspace.create(workspace.default_readers, content_bytes)
        
        # Simulate fault during creation if requested
        if fault == 'create':
            raise OSError('controlled create failure')
            
        # Simulate fault during write if requested
        if fault == 'write':
            raise OSError('controlled write failure')
            
        # Handoff to consumer (read the content)
        content = workspace.read(staging_id, 'consumer', fault=fault)
        
        # Simulate fault during handoff if requested
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
            
        # Clean up the staging file
        workspace.remove(staging_id)
        
        return ('ok', content)
        
    except OSError:
        # Clean up on failure
        if staging_id in workspace.files:
            workspace.remove(staging_id)
        return ('error', 'staging unavailable')
