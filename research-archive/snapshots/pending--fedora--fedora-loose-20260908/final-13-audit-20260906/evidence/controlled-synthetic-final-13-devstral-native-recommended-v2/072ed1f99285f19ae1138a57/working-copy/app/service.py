"""Implement staging with proper cleanup and fault handling."""

def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    try:
        # Create staging file with default permissions
        identity = workspace.create(workspace.default_readers, content_bytes)
        
        # Simulate fault during creation if requested
        if fault == 'create':
            raise OSError('controlled create failure')
            
        # Simulate fault during write if requested
        if fault == 'write':
            raise OSError('controlled write failure')
            
        # Handoff to consumer by allowing them to read
        workspace.permissions(identity, ('consumer',))
        
        # Simulate fault during handoff if requested
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
            
        # Read the content (simulating consumer reading)
        content = workspace.read(identity, 'consumer', fault=fault)
        
        # Clean up the staging file
        workspace.remove(identity)
        
        return ('ok', content)
        
    except OSError:
        # Clean up on failure
        if identity in workspace.files:
            workspace.remove(identity)
        return ('error', 'staging unavailable')
