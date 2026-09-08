"""Stage content for a single, explicit consumer and always clean it up."""


def run(workspace, content_bytes, fault=None):
    """Deliver ``content_bytes`` through a temporary producer-only staging file.

    The staging object is deliberately not left accessible after either a
    successful handoff or an error at any point in the lifecycle.
    """
    identity = None

    try:
        if fault == 'create':
            raise OSError('controlled create failure')

        # Staging is initially visible only to its producer.
        identity = workspace.create(('producer',), content_bytes)

        if fault == 'write':
            raise OSError('controlled write failure')
        if fault == 'handoff':
            raise OSError('controlled handoff failure')

        # Handoff replaces, rather than expands, the staging permissions.
        workspace.permissions(identity, ('consumer',))
        delivered = workspace.read(identity, 'consumer', fault)
        if delivered is None:
            raise OSError('consumer could not read staged content')
        return ('ok', delivered)
    except Exception as error:
        return ('error', str(error))
    finally:
        if identity is not None:
            workspace.remove(identity)
