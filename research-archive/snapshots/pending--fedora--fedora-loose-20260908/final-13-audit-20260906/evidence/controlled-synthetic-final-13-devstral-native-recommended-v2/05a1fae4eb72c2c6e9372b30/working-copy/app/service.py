"""Implementation with staging, handoff, and cleanup."""

def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')
    
    identity = None
    try:
        # Stage the content
        if fault == 'create':
            raise OSError('controlled create failure')
        identity = workspace.create(('producer',), content_bytes)
        
        # Write to staging area
        if fault == 'write':
            raise OSError('controlled write failure')
        
        # Handoff to consumer
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(identity, ('consumer',))
        
        # Read the content
        if fault == 'read':
            raise OSError('controlled read failure')
        content = workspace.read(identity, 'consumer')
        
        return ('ok', content)
    except OSError:
        return ('error', 'operation failed')
    finally:
        # Cleanup
        if identity is not None and identity in workspace.files:
            workspace.remove(identity)
