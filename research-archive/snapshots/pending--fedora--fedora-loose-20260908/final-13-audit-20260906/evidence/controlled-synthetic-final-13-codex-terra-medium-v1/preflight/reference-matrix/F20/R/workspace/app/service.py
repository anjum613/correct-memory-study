from urllib.parse import urljoin, urlsplit


def _origin(url):
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower() if parsed.hostname is not None else None
    port = parsed.port
    if port is None:
        port = {"http": 80, "https": 443}.get(scheme)
    return scheme, host, port


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external:
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("external resource URL must be absolute")
    elif parsed.scheme or parsed.netloc:
        raise ValueError("absolute resource URLs require external=True")

    url = urljoin(session.origin, reference)
    credentials = None
    if _origin(url) == _origin(session.origin):
        credentials = session.cookie
    return transport.fetch(url, credentials=credentials)
