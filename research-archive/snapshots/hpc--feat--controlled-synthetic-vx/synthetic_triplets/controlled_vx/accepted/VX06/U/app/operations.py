"""Implementation helpers for this application."""


def normalize_origin(origin):
    if not isinstance(origin, tuple) or len(origin) != 3:
        raise ValueError('invalid origin tuple')
    scheme, host, port = origin
    if not isinstance(scheme, str) or scheme.lower() not in ('http', 'https'):
        raise ValueError('invalid origin scheme')
    if not isinstance(host, str) or not host:
        raise ValueError('invalid origin host')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid origin port')
    return (scheme.lower(), host.lower(), port)
