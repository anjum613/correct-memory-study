from urllib.parse import urljoin, urlsplit

def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external:
        if not (parsed.scheme and parsed.netloc):
            raise ValueError("external URLs must be absolute")
        url = reference
    else:
        if parsed.scheme or parsed.netloc:
            raise ValueError("absolute resource URLs require external=True")
        url = urljoin(session.origin, reference)
    
    return transport.fetch(url, credentials=session.cookie)
