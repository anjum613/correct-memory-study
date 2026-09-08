"""Stage content, hand it to the consumer, and clean the staging file up."""


def run(workspace, content_bytes, fault=None):
    # Keep the existing fast path: empty content does not need a staging file.
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # The staged object is initially visible only to the producer.
        identity = workspace.create({'producer'}, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        # Handoff is explicit: replace producer access with consumer access.
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(identity, {'consumer'})

        result = workspace.read(identity, 'consumer', fault=fault)
        if result is None:
            raise PermissionError('consumer cannot read staged content')
        return ('ok', result)
    except BaseException as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
