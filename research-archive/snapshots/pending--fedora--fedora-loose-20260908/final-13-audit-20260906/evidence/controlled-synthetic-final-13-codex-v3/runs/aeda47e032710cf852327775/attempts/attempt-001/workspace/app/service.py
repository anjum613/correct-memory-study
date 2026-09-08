"""Stage content, hand it to the consumer, and always clean it up."""


def run(workspace, content_bytes, fault=None):
    # Preserve the existing no-op behavior for empty content.
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # Do not inherit the workspace's broad default readers: staging is
        # producer-private until the explicit handoff below.
        identity = workspace.create({'producer'}, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')
        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        workspace.permissions(identity, {'consumer'})
        result = workspace.read(identity, 'consumer', fault)
        return ('ok', result)
    except BaseException as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
