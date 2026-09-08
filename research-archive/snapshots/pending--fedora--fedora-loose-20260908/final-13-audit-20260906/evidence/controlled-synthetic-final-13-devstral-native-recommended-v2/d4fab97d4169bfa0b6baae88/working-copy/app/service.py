"""Implement staging, handoff, and cleanup functionality."""

def run(workspace, content_bytes, fault=None):
    # Handle empty content case
    if content_bytes == b'':
        return ('ok', b'')
    
    # Create a staging file with producer permissions
    try:
        staging_id = workspace.create(('producer',), content_bytes)
    except Exception:
        return ('error', 'staging unavailable')

    # Simulate the fault if specified
    if fault == 'create':
        workspace.remove(staging_id)
        return ('error', 'staging unavailable')
    if fault == 'write':
        workspace.remove(staging_id)
        return ('error', 'staging unavailable')

    # Change permissions to allow consumer access (handoff)
    try:
        workspace.permissions(staging_id, ('producer', 'consumer'))
    except Exception:
        # Clean up if handoff fails
        workspace.remove(staging_id)
        return ('error', 'handoff unavailable')

    # Simulate the fault if specified
    if fault == 'handoff':
        workspace.remove(staging_id)
        return ('error', 'handoff unavailable')

    # Read the content for the consumer
    try:
        content = workspace.read(staging_id, 'consumer', fault=fault)
        if content is None:
            workspace.remove(staging_id)
            return ('error', 'content unavailable')
    except Exception:
        # Clean up if read fails
        workspace.remove(staging_id)
        return ('error', 'content unavailable')

    # Clean up the staging file
    workspace.remove(staging_id)
    
    return ('ok', content)
