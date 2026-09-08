"""Staging service implementation."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    staged = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        if fault == 'write':
            staged = workspace.create({'producer'}, b'')
            raise OSError('controlled write failure')
        staged = workspace.create({'producer'}, content_bytes)

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(staged, {'consumer'})

        data = workspace.read(staged, 'consumer', fault=fault)
        if data is None:
            return ('error', 'consumer could not read staged content')
        return ('ok', data)
    except OSError as error:
        return ('error', str(error))
    finally:
        if staged is not None:
            workspace.remove(staged)
