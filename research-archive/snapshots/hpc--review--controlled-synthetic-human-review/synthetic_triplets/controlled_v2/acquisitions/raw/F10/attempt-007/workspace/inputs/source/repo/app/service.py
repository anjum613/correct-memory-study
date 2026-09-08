from urllib.parse import urljoin

from app.dependencies import INTEGRATION_BASE


def fetch_internal(reference: str, transport):
    url = urljoin(INTEGRATION_BASE, reference)
    return transport.get(url)
