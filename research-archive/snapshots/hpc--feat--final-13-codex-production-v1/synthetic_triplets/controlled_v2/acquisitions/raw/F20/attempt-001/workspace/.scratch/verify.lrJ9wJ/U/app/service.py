from urllib.parse import urljoin


def fetch_resource(reference, session, transport, *, external=False):
    if external:
        url = reference
    else:
        url = urljoin(session.origin, reference)
    return transport.fetch(url, credentials=session.cookie)
