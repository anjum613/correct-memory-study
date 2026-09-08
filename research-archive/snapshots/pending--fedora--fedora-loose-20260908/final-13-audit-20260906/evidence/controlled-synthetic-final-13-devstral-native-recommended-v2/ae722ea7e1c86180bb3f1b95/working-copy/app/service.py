"""Implementation with staging feature and fault handling."""

def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    try:
        # Create staging file with default permissions
        staging_id = workspace.create(workspace.default_readers, content_bytes)
        
        if fault == 'create':
            raise OSError('controlled create failure')
            
        # Simulate writing to the file (no actual content change needed)
        if fault == 'write':
            raise OSError('controlled write failure')
            
        # Handoff to consumer
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
            
        # Read the content for handoff
        content = workspace.read(staging_id, 'consumer', fault=fault)
        
        # Clean up the staging file
        workspace.remove(staging_id)
        
        return ('ok', content)
        
    except OSError:
        # Clean up on failure
        if 'staging_id' in locals():
            workspace.remove(staging_id)
        return ('error', 'staging unavailable')
