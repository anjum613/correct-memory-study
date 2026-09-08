"""Service routine for staging content, handing it to a consumer, and cleaning up."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        identity = workspace.create({'producer'}, content_bytes)

        try:
            if fault == 'write':
                raise OSError('controlled write failure')

            workspace.permissions(identity, {'consumer'})

            if fault == 'handoff':
                raise OSError('controlled handoff failure')

            value = workspace.read(identity, 'consumer', fault=fault)
            return ('ok', value)
        finally:
            workspace.remove(identity)
    except BaseException:
        return ('error', 'staging unavailable')
