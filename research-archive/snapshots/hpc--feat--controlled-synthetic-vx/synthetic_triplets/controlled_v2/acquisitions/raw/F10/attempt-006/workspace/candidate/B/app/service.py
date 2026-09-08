from urllib.parse import urljoin


def fetch_resource(reference: str, config, transport, base_url: str | None = None):
    if base_url is not None:
        raise NotImplementedError("custom integration bases are not implemented")

    url = urljoin(config.default_base, reference)
    return transport.get(url)
