"""Stage content, hand it to the consumer, and clean it up reliably."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    staging_id = None
    try:
        if fault == 'create':
            return ('error', fault)

        # The staging object deliberately inherits the workspace defaults.
        # This is the producer's normal, authorized staging context.
        staging_id = workspace.create(workspace.default_readers, content_bytes)

        if fault == 'write':
            return ('error', fault)
        if fault == 'handoff':
            return ('error', fault)

        # Handoff is an explicit permission transition to the designated
        # consumer, rather than relying on the inherited staging permissions.
        workspace.permissions(staging_id, {'consumer'})
        result = workspace.read(staging_id, 'consumer', fault=fault)
        if result is None:
            return ('error', 'handoff denied')
        return ('ok', result)
    except Exception as error:
        return ('error', str(error))
    finally:
        if staging_id is not None:
            workspace.remove(staging_id)
