"""Baseline with empty-content behavior and no staging feature."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    staged = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')
        staged = workspace.create((), content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(staged, ('consumer',))

        delivered = workspace.read(staged, 'consumer', fault=fault)
        if delivered is None:
            return ('error', 'consumer cannot read staged content')
        return ('ok', delivered)
    except Exception as error:
        return ('error', str(error))
    finally:
        if staged is not None:
            workspace.remove(staged)
