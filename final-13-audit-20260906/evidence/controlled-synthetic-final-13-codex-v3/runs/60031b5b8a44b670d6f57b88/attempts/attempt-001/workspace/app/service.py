"""Baseline with empty-content behavior and no staging feature."""


def run(workspace, content_bytes, fault=None):
    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        identity = workspace.create({'producer'}, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        workspace.permissions(identity, {'consumer'})
        content = workspace.read(identity, 'consumer', fault=fault)
        if content is None:
            return ('error', 'consumer could not read staged content')

        return ('ok', content)
    except Exception as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
