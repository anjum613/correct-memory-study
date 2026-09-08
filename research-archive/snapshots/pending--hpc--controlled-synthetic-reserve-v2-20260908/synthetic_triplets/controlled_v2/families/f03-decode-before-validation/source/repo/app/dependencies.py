import posixpath


class ResourceStore:
    def __init__(self, resources):
        self.resources = dict(resources)

    def read(self, path):
        return self.resources[posixpath.normpath(path)]
