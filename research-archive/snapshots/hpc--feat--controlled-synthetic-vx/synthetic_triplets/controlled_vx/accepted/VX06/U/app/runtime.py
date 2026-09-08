from dataclasses import dataclass
@dataclass(frozen=True)
class Session:
    origin: tuple
    marker: str
class Transport:
    def __init__(self):
        self.calls = []
    def fetch(self, origin, path, *, marker):
        self.calls.append((origin, path, marker))
        return origin[1] + ':' + path
