class AuditSink:
    def __init__(self):
        self.records = []

    def append(self, text):
        self.records.append(text)
