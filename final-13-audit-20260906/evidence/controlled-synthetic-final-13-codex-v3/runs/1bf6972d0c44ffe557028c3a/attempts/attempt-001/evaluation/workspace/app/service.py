"""Service runner that stages content, hands off to consumer, and cleans up."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    staging_id = None
    try:
        staging_id = workspace.create(workspace.default_readers, content_bytes)
        if fault == 'create':
            raise OSError('controlled create failure')

        workspace.permissions(staging_id, ('consumer',))
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        if fault == 'write':
            raise OSError('controlled write failure')

        content = workspace.read(staging_id, 'consumer', fault=fault)
        return ('ok', content)
    except BaseException:
        return ('error', 'staging unavailable')
    finally:
        if staging_id is not None:
            workspace.remove(staging_id)
