from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    if external and (parsed.scheme or parsed.netloc):
        # Absolute URL with external=True: fetch directly
        url = reference
    elif not external and (parsed.scheme or parsed.netloc):
        # Absolute URL without external=True: raise error
        raise ValueError("absolute resource URLs require external=True")
    else:
        # Relative URL: resolve against session origin
        url = urljoin(session.origin, reference)

    return transport.fetch(url, credentials=session.cookie)
