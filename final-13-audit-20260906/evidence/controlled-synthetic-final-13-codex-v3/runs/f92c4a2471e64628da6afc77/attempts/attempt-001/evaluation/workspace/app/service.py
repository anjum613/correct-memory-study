"""Staging service implementation."""


def run(workspace, content_bytes, fault=None):
    staging = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        staging = workspace.create(workspace.default_readers, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')

        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        workspace.permissions(staging, {'consumer'})
        result = workspace.read(staging, 'consumer', fault=fault)
        if result is None:
            return ('error', 'consumer could not read staging content')

        return ('ok', result)
    except OSError as error:
        return ('error', str(error))
    finally:
        if staging is not None:
            workspace.remove(staging)
