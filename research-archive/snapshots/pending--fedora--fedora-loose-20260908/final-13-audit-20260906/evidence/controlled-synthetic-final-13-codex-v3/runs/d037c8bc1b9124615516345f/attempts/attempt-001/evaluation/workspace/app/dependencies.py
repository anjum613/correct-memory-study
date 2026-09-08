import posixpath


class ExportStore:
    def __init__(self):
        self.writes = {}

    def write(self, relative_name, body):
        absolute = posixpath.normpath(posixpath.join("/exports", relative_name))
        self.writes[absolute] = body
