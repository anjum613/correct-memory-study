from urllib.parse import urljoin, urlsplit


def fetch_resource(reference, session, transport):
    parsed_reference = urlsplit(reference)
    if parsed_reference.scheme or parsed_reference.netloc:
        raise ValueError("external references are not supported")

    url = urljoin(session.origin, reference)
    return transport.fetch(url, credentials=session.cookie)
