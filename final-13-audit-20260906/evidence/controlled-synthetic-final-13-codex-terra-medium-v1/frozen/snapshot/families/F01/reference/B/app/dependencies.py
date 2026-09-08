class PayloadSink:
    def __init__(self):
        self.items = []

    def store(self, payload: bytes) -> None:
        self.items.append(payload)
