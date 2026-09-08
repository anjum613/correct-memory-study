from app.models import HttpResponse


class IntegrationConfig:
    def __init__(self, default_base, allowed_origins):
        self.default_base = default_base
        self.allowed_origins = frozenset(allowed_origins)


class Transport:
    def __init__(self):
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        return HttpResponse(url=url, body="ok")
