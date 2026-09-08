from urllib.parse import urljoin

from app.models import Redirect


def redirect_to(route: str, config) -> Redirect:
    return Redirect(location=urljoin(config.origin, route))
