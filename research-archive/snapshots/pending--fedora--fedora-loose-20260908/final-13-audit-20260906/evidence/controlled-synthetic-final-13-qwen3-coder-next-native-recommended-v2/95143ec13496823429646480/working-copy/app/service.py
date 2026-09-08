from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external:
        url = reference
    elif parsed.scheme or parsed.netloc:
        raise ValueError("absolute resource URLs require external=True")
    else:
        url = urljoin(session.origin, reference)
    
    return transport.fetch(url, credentials=session.cookie)
