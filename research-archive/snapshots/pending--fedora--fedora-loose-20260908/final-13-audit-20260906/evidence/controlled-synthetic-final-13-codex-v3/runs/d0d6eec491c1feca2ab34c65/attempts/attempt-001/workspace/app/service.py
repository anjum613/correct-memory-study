"""Staged content handoff service."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        identity = workspace.create({'producer'}, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(identity, {'consumer'})

        delivered = workspace.read(identity, 'consumer', fault=fault)
        if delivered is None:
            return ('error', 'handoff denied')
        return ('ok', delivered)
    except Exception as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
