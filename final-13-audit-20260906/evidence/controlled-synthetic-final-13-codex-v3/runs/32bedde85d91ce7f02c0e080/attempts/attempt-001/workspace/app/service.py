"""Staged content handoff service."""


def run(workspace, content_bytes, fault=None):
    staged = None

    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        staged = workspace.create(('producer',), content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        workspace.permissions(staged, ('consumer',))
        content = workspace.read(staged, 'consumer', fault=fault)

        if content is None:
            return ('error', 'consumer cannot read staged content')

        return ('ok', content)
    except Exception as error:
        return ('error', str(error))
    finally:
        if staged is not None:
            workspace.remove(staged)
