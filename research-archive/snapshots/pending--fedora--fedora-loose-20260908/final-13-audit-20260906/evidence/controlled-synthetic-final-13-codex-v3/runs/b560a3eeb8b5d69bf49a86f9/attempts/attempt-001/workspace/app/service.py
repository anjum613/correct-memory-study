"""Service implementation for staging payloads and handing off to consumers."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    staging_identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        staging_identity = workspace.create(('producer',), content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        workspace.permissions(staging_identity, ('consumer',))

        read_fault = 'read' if fault == 'read' else None
        payload = workspace.read(staging_identity, 'consumer', fault=read_fault)
        if payload is None:
            raise OSError('permission denied')

        return ('ok', payload)
    except BaseException as error:
        return ('error', str(error))
    finally:
        if staging_identity is not None:
            workspace.remove(staging_identity)
