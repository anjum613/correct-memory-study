import posixpath
class VirtualStore:
    def __init__(self):
        self.entries = {}
        self.commits = 0
    def address(self, name):
        return posixpath.normpath(posixpath.join('/exports', name))
    def commit(self, rows):
        self.commits += 1
        self.entries.update({self.address(name): body for name, body in rows})
