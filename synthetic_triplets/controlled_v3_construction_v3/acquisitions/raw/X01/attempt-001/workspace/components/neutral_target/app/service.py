"""Baseline report service with replacement unavailable."""


def run(directory, name, data):
    try:
        identity = directory.lookup(name)
        if identity is None:
            return 'missing'
        if directory.attributes(identity).get('owner') != 'writer':
            return 'denied'
        return 'unavailable'
    except Exception:
        return 'error'
