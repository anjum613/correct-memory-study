class MemorySink:
    def __init__(self):
        self.batches = []
    def commit(self, rows):
        self.batches.append([dict(row) for row in rows])
