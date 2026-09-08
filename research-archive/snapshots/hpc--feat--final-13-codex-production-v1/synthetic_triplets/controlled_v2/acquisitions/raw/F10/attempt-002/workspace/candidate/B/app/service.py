from urllib.parse import urljoin


def fetch_resource(reference: str, config, transport, base_url=None):
    if base_url is not None:
        raise ValueError("custom integration bases are not supported")

    url = urljoin(config.default_base, reference)
    return transport.get(url)
