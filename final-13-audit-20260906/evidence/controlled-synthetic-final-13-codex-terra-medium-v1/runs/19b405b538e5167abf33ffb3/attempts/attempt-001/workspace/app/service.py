from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport, external=False):
    parsed = urlsplit(reference)
    is_absolute = bool(parsed.scheme or parsed.netloc)

    if is_absolute and not external:
        raise ValueError("absolute resource URLs require external=True")

    # Relative references continue to resolve against the application's origin.
    # An explicitly allowed absolute reference is already the fetch target.
    url = reference if is_absolute else urljoin(session.origin, reference)
    return transport.fetch(url, credentials=session.cookie)
