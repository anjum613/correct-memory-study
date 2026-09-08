from app.models import FetchResult


class Transport:
    def __init__(self):
        self.calls = []

    def fetch(self, url, *, credentials):
        self.calls.append((url, credentials))
        return FetchResult(url=url, body="resource")
