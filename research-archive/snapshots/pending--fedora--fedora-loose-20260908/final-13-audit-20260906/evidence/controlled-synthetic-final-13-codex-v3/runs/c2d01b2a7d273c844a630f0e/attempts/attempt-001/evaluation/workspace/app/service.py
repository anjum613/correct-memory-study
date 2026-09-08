"""Service implementation for staging-and-handoff content transfer."""


def run(workspace, content_bytes, fault=None):
    if content_bytes == b'':
        return ('ok', b'')

    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # Stage the content for initial inspection, then retain it during handoff.
        identity = workspace.create(workspace.default_readers, content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')
        workspace.permissions(identity, ('producer',))

        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        workspace.permissions(identity, ('consumer',))

        content = workspace.read(
            identity,
            'consumer',
            'read' if fault == 'read' else None,
        )
        if content is None:
            raise OSError('controlled read failure')
        return ('ok', content)
    except BaseException:
        return ('error', 'staging unavailable')
    finally:
        if identity is not None:
            try:
                workspace.remove(identity)
            except BaseException:
                pass
