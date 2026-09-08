from urllib.parse import urljoin


def fetch_resource(reference: str, config, transport):
    url = urljoin(config.default_base, reference)
    return transport.get(url)
