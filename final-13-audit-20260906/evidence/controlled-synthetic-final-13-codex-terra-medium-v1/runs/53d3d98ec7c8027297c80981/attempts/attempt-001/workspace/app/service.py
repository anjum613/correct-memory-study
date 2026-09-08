"""Stage content privately before handing it to its consumer."""


def run(workspace, content_bytes, fault=None):
    """Return the content after a private staging and consumer handoff.

    A staging file must never inherit the workspace's ambient readers: those
    readers are not necessarily authorised for this particular payload.  It is
    created for the producer alone, then explicitly transferred to the named
    consumer.  Removal lives in ``finally`` so every post-creation failure has
    the same cleanup behaviour as the successful path.
    """
    # This is the established no-content fast path; in particular, it does not
    # create a pointless temporary file.
    if content_bytes == b'':
        return ('ok', b'')

    staging_id = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # Do not use workspace.default_readers here.  Its membership is an
        # ambient policy, whereas this payload has one intended recipient.
        staging_id = workspace.create({'producer'}, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(staging_id, {'consumer'})

        delivered = workspace.read(staging_id, 'consumer', fault=fault)
        if delivered is None:
            raise OSError('consumer could not read staged content')
        return ('ok', delivered)
    except OSError as error:
        return ('error', str(error))
    finally:
        if staging_id is not None:
            workspace.remove(staging_id)
