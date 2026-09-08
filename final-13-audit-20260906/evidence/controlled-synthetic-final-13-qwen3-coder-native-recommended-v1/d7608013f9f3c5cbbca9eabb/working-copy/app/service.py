from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external:
        # When external=True, fetch absolute URLs directly
        if parsed.scheme or parsed.netloc:
            return transport.fetch(reference, credentials=session.cookie)
        else:
            # For relative URLs with external=True, resolve against session origin
            url = urljoin(session.origin, reference)
            return transport.fetch(url, credentials=session.cookie)
    
    # Default behavior: relative URLs only, resolve against session origin
    if parsed.scheme or parsed.netloc:
        raise ValueError("absolute resource URLs require external=True")

    url = urljoin(session.origin, reference)
    return transport.fetch(url, credentials=session.cookie)
