class Workspace:
    def __init__(self, documents):
        self.documents = dict(documents)

    def read(self, document_id):
        return self.documents[document_id]


class Broker:
    def __init__(self, workspaces):
        self.workspaces = dict(workspaces)

    def open(self, name):
        return self.workspaces[name]
