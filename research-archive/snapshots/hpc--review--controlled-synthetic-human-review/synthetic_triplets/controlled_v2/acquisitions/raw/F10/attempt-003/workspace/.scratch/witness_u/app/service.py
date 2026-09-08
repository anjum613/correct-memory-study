from urllib.parse import urljoin


def fetch_resource(reference: str, config, transport, base_url=None):
    base = config.default_base if base_url is None else base_url
    url = urljoin(base, reference)
    return transport.get(url)
