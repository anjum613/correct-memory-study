"""Staging implementation with proper cleanup and fault handling."""

def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    try:
        # Create staging file with default permissions
        staging_id = workspace.create(workspace.default_readers, content_bytes)
        
        # Simulate fault during staging if requested
        if fault == 'create':
            raise OSError('controlled create failure')
        if fault == 'write':
            raise OSError('controlled write failure')
        
        # Read the content to simulate handoff
        content = workspace.read(staging_id, 'consumer', fault=fault)
        if fault == 'read':
            raise OSError('controlled read failure')
        
        # Simulate handoff fault
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        
        # Successful handoff
        return ('ok', content)
        
    except OSError:
        # Clean up on failure
        if 'staging_id' in locals():
            workspace.remove(staging_id)
        return ('error', 'staging unavailable')
    finally:
        # Ensure cleanup happens even if no exception
        if 'staging_id' in locals():
            workspace.remove(staging_id)
