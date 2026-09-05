"""Replace report contents through the authorized object reference."""


def run(directory, name, data):
    temporary = None
    try:
        identity = directory.lookup(name)
        if identity is None:
            return 'missing'

        # Retain the object itself as well as its entry identity. A later
        # pathname lookup must never choose the object that receives the write.
        objects = directory.objects
        target = objects[identity]
        if directory.attributes(identity).get('owner') != 'writer':
            return 'denied'

        def still_authorized():
            return (
                directory.objects is objects
                and directory.lookup(name) == identity
                and objects.get(identity) is target
                and target.get('owner') == 'writer'
            )

        directory.hook('after_check')
        if not still_authorized():
            return 'denied'

        temporary = directory.stage(data)
        directory.hook('after_stage')
        if not still_authorized():
            return 'denied'
        if directory.fail_commit:
            raise OSError('controlled replacement failure')

        # Commit to the retained, checked object; replace_path would resolve
        # the mutable directory entry again and could modify another object.
        target['data'] = directory.temporary[temporary]
        directory.events.append(('replace', identity))
        return 'updated'
    except Exception:
        return 'error'
    finally:
        if temporary is not None:
            directory.discard(temporary)
