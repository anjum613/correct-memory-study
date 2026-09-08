"""Stage content privately, hand it to the consumer, and always clean up."""


def run(workspace, content_bytes, fault=None):
    """Deliver *content_bytes* through a short-lived staging file.

    A staging file must not inherit the workspace's broadly useful default
    readers: it contains the payload before the intended consumer has taken
    ownership.  It is therefore created for the producer, then explicitly
    handed to the consumer.  The ``finally`` block covers every point after a
    file exists, including controlled failures used by the harness.
    """
    if content_bytes == b'':
        return ('ok', b'')

    staging_id = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # The fixture represents creation and writing as one operation.  Give
        # the producer sole access while the bytes first enter staging.
        staging_id = workspace.create({'producer'}, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        # Deliberately transfer access to the designated consumer only.
        workspace.permissions(staging_id, {'consumer'})
        delivered = workspace.read(staging_id, 'consumer', fault=fault)
        if delivered != content_bytes:
            raise OSError('staging content mismatch')
        return ('ok', delivered)
    except OSError as error:
        return ('error', str(error))
    finally:
        if staging_id is not None:
            workspace.remove(staging_id)
