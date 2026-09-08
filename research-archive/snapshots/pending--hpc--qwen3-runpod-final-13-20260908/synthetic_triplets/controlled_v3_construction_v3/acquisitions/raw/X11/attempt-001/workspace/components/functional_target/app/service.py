"""Stage content with explicit access and unconditional cleanup."""


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
        workspace.permissions(identity, {'producer', 'consumer'})
        content = workspace.read(identity, 'consumer', fault)
        return ('ok', content)
    except Exception as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
