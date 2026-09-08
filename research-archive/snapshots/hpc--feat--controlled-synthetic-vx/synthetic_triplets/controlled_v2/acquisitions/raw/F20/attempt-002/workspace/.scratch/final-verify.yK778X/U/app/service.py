from urllib.parse import urljoin


def fetch_resource(resource, session, transport, external=False):
    url = urljoin(session.origin, resource)
    return transport.fetch(url, credentials=session.cookie)
