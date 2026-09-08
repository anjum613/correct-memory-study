"""Safely stage content before handing it to the designated consumer."""


def run(workspace, content_bytes, fault=None):
    """Stage *content_bytes*, hand it to ``consumer``, and always clean up.

    A staging entry must not inherit the workspace's default readers: those
    readers can include identities other than the intended recipient.  It is
    therefore created with no readers and made readable by ``consumer`` only
    at the handoff point.
    """
    # Retain the original no-op handling of empty content.
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # Nothing may observe the staged bytes before the explicit handoff.
        identity = workspace.create((), content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')
        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        workspace.permissions(identity, ('consumer',))
        received = workspace.read(identity, 'consumer', fault=fault)
        if received is None:
            return ('error', 'consumer could not read staged content')
        return ('ok', received)
    except OSError as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
