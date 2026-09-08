"""Workflow that stages payloads for consumer handoff with cleanup."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    staged_identity = None
    try:
        staged_identity = workspace.create(workspace.default_readers, content_bytes)
        if fault == 'create':
            raise OSError('controlled create failure')

        if fault == 'write':
            if hasattr(workspace, 'write'):
                workspace.write(staged_identity, content_bytes)
            else:
                raise OSError('controlled write failure')

        if hasattr(workspace, 'permissions'):
            workspace.permissions(staged_identity, {'consumer'})
            if fault == 'handoff':
                raise OSError('controlled handoff failure')

        delivered = workspace.read(staged_identity, 'consumer', fault=fault)
        if delivered != content_bytes:
            raise OSError('unexpected payload delivered')

        return ('ok', delivered)
    except BaseException:
        return ('error', 'staging unavailable')
    finally:
        if staged_identity is not None:
            workspace.remove(staged_identity)
