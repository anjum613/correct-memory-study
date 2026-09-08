from app.models import EventReceipt


class EventHandler:
    def __init__(self):
        self.calls = []

    def handle(self, body):
        self.calls.append(body)
        return EventReceipt(body=body, accepted=True)


class SignatureVerifier:
    def __init__(self, accepted):
        self.accepted = frozenset(accepted)

    def verify(self, body, signature):
        return (body, signature) in self.accepted
