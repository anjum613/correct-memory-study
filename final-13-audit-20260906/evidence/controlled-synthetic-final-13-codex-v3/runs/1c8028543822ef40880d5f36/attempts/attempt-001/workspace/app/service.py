"""Staged content handoff implementation."""


def run(workspace, content_bytes, fault=None):
    staging = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        if fault == 'write':
            staging = workspace.create({'producer'}, b'')
            raise OSError('controlled write failure')

        staging = workspace.create({'producer'}, content_bytes)

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(staging, {'consumer'})

        content = workspace.read(staging, 'consumer', fault=fault)
        if content is None:
            return ('error', 'consumer cannot read staging')
        return ('ok', content)
    except OSError as error:
        return ('error', str(error))
    finally:
        if staging is not None:
            workspace.remove(staging)
