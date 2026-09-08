MAX_EXPANDED_BYTES = 64


class ArchiveEntry:
    def __init__(self, name, body, expanded_size=None):
        self.name = name
        self._body = body
        self.expanded_size = len(body) if expanded_size is None else expanded_size
        self.read_calls = 0

    def read(self):
        self.read_calls += 1
        return self._body


class Archive:
    def __init__(self, entries):
        self.entries = tuple(entries)


class ExtractionSink:
    def __init__(self):
        self.files = {}

    def write(self, name, body):
        self.files[name] = body
