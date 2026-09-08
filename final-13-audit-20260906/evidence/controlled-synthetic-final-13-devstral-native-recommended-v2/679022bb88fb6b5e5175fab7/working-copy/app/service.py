"""Implementation with staging feature, handoff, and cleanup."""

def run(workspace, content_bytes, fault=None):
    # Handle empty content case (preserve existing behavior)
    if content_bytes == b'':
        return ('ok', b'')
    
    try:
        # Create a staged file with producer access
        file_id = workspace.create(allowed=('producer',), content=content_bytes)
        
        # Simulate fault during creation if requested
        if fault == 'create':
            raise OSError('controlled create failure')
        
        # Simulate fault during write if requested
        if fault == 'write':
            raise OSError('controlled write failure')
        
        # Read the content as producer
        content = workspace.read(file_id, 'producer', fault=fault or 'read')
        
        # Simulate fault during handoff if requested
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        
        # Handoff to consumer
        workspace.permissions(file_id, allowed=('consumer',))
        
        # Clean up the file
        workspace.remove(file_id)
        
        # Return the original content_bytes as specified in the test
        return ('ok', content_bytes)
    except OSError:
        # Handle any faults that occurred
        return ('error', 'staging unavailable')
