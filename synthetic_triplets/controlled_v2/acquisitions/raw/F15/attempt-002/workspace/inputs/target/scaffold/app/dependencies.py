class AuditCallback:
    def __init__(self):
        self.events = []

    def __call__(self, account):
        self.events.append(account)
