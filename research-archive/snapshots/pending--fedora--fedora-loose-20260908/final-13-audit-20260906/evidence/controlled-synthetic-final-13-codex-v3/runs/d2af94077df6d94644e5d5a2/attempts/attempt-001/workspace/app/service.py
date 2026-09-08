"""Stage content, hand it to its consumer, and clean up the staging file."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    staging = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # Creation uses the workspace's inherited default access policy.
        staging = workspace.create(workspace.default_readers, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        # The consumer is granted access explicitly at handoff time.
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(staging, {'consumer'})

        result = workspace.read(staging, 'consumer', fault=fault)
        return ('ok', result)
    except BaseException as error:
        return ('error', str(error))
    finally:
        if staging is not None:
            workspace.remove(staging)
