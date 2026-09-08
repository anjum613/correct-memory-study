"""Implement staging feature with proper handoff and cleanup."""

def run(workspace, content_bytes, fault=None):
    # If fault is specified, return error immediately
    if fault:
        return ('error', f'fault: {fault}')
    
    try:
        # Stage the content with producer access
        identity = workspace.create(('producer',), content_bytes)
        
        # Handoff to consumer
        workspace.permissions(identity, ('consumer',))
        
        # Read the content as consumer
        content = workspace.read(identity, 'consumer')
        
        # Clean up
        workspace.remove(identity)
        
        if content is None:
            return ('error', 'content unavailable')
        return ('ok', content)
    except OSError:
        # Handle any workspace errors
        return ('error', 'workspace error')
    finally:
        # Ensure cleanup happens even if there's an error
        try:
            workspace.remove(identity)
        except:
            pass
