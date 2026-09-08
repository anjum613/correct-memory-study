from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external:
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("external resource URL must be absolute")
    elif parsed.scheme or parsed.netloc:
        raise ValueError("absolute resource URLs require external=True")

    url = urljoin(session.origin, reference)
    return transport.fetch(url, credentials=session.cookie)
