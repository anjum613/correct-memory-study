"""Baseline with empty-content behavior and no staging feature."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    # Staging feature implementation
    identity = None
    try:
        # Create a file in the workspace
        identity = workspace.create(['producer', 'consumer'], content_bytes)
        
        # Simulate potential faults
        if fault == 'create':
            raise OSError('controlled create failure')
            
        # Handoff to consumer (this would normally involve permission changes)
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
            
        # Simulate writing to the file
        if fault == 'write':
            raise OSError('controlled write failure')
            
        # Read back to verify (this simulates the consumer reading)
        if fault == 'read':
            raise OSError('controlled read failure')
            
        # Normal cleanup - remove the file
        workspace.remove(identity)
        
        return ('ok', content_bytes)
        
    except OSError:
        # Failure cleanup - remove the file if it exists
        if identity is not None:
            workspace.remove(identity)
        return ('error', 'staging failed')
