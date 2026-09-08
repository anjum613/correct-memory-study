from urllib.parse import urljoin


def fetch_same_origin(reference, session, transport):
    url = urljoin(session.origin, reference.value)
    return transport.fetch(url, credentials=session.cookie)
