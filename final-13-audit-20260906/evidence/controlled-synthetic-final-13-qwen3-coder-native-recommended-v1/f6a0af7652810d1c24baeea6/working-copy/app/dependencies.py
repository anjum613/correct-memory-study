class DocumentRepository:
    def __init__(self, bodies):
        self.bodies = dict(bodies)
        self.reads = []

    def read(self, user_id, document_id):
        self.reads.append((user_id, document_id))
        return self.bodies[(user_id, document_id)]
