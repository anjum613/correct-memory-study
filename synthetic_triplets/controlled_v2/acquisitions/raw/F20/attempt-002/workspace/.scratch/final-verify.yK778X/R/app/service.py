from urllib.parse import urljoin, urlsplit


def _origin(url):
    parsed = urlsplit(url)
    port = parsed.port
    if port is None:
        port = {"http": 80, "https": 443}.get(parsed.scheme.lower())
    return parsed.scheme.lower(), parsed.hostname, port


def fetch_resource(resource, session, transport, external=False):
    url = urljoin(session.origin, resource)
    credentials = session.cookie if _origin(url) == _origin(session.origin) else None
    return transport.fetch(url, credentials=credentials)
