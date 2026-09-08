from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    
    if parsed.scheme or parsed.netloc:
        if not external:
            raise ValueError("absolute resource URLs require external=True")
        url = reference
    else:
        url = urljoin(session.origin, reference)
    
    return transport.fetch(url, credentials=session.cookie)
