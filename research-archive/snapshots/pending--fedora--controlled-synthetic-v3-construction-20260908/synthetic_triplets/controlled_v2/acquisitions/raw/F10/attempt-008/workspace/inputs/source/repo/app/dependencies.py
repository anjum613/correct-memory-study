from app.models import HttpResponse


INTEGRATION_BASE = "https://api.internal.test/v1/"


class Transport:
    def __init__(self):
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        return HttpResponse(url=url, body="ok")
