"""Stage content privately, hand it to the consumer, and always clean up."""


def run(workspace, content_bytes, fault=None):
    """Deliver *content_bytes* through a short-lived, private staging file.

    Empty content retains the historical no-op behaviour.  For non-empty
    content, staging is visible only to the producer until the explicit
    handoff, after which it is visible only to the designated consumer.
    """
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # Do not create the staged content with the workspace's broad default
        # readership: it is private until the handoff is intentional.
        identity = workspace.create({'producer'}, content_bytes)

        # The fixture models writing as part of creation.  Keep a distinct
        # failure point so a failed write still exercises cleanup.
        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(identity, {'consumer'})

        delivered = workspace.read(identity, 'consumer', fault=fault)
        if delivered is None:
            return ('error', 'consumer cannot read staged content')
        return ('ok', delivered)
    except OSError as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
