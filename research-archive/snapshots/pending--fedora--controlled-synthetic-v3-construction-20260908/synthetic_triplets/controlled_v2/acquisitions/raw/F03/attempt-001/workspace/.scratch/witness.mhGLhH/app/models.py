import posixpath
from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalResourcePath:
    value: str

    def __post_init__(self):
        if posixpath.normpath(self.value) != self.value:
            raise ValueError("path is not canonical")


@dataclass(frozen=True)
class Resource:
    path: str
    body: str
