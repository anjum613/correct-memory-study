from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external:
        url = reference if (parsed.scheme or parsed.netloc) else urljoin(session.origin, reference)
    else:
        if parsed.scheme or parsed.netloc:
            raise ValueError("absolute resource URLs require external=True")
        url = urljoin(session.origin, reference)
    return transport.fetch(url, credentials=session.cookie)
