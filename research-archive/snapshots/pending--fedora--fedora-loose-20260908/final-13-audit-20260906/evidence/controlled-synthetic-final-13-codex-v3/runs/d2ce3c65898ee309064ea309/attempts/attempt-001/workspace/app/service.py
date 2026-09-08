"""Stage content, hand it to the consumer, and clean up the staging object."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        # The fault argument is part of the fixture's controlled-failure API.
        # Check failures before creating anything so failed writes cannot leave
        # a partially staged object behind.
        if fault == 'create' or fault == 'write':
            raise OSError('controlled staging failure')

        identity = workspace.create(workspace.default_readers, content_bytes)

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(identity, {'consumer'})

        result = workspace.read(identity, 'consumer', fault=fault)
        return ('ok', result)
    except BaseException as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
