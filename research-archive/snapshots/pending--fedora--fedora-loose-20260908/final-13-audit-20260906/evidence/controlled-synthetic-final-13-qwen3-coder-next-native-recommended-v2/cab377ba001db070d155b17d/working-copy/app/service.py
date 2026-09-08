"""Service implementation with staging, handoff, and cleanup."""


def run(workspace, content_bytes, fault=None):
    # Empty content: return immediately (no staging needed)
    if content_bytes == b'':
        return ('ok', b'')
    
    # Staging: create a file in the workspace
    # Use default readers (producer, consumer) to allow handoff
    identity = workspace.create(workspace.default_readers, content_bytes)
    
    try:
        # Handoff: consumer reads the staged content
        # Read as consumer to verify handoff works
        consumer_content = workspace.read(identity, 'consumer', fault)
        if consumer_content is None:
            raise OSError('handoff failed')
        
        # Normal cleanup: remove the staged file
        workspace.remove(identity)
        return ('ok', content_bytes)
    except OSError:
        # Failure cleanup: remove the staged file on error
        workspace.remove(identity)
        return ('error', 'staging unavailable')
