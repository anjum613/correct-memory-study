from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external and (parsed.scheme or parsed.netloc):
        # External absolute URL - fetch directly
        return transport.fetch(reference, credentials=session.cookie)
    elif parsed.scheme or parsed.netloc:
        raise ValueError("absolute resource URLs require external=True")

    url = urljoin(session.origin, reference)
    return transport.fetch(url, credentials=session.cookie)
