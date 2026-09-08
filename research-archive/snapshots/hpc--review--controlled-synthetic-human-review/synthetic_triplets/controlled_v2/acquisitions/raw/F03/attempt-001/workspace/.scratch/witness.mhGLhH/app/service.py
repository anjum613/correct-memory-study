import posixpath
from urllib.parse import unquote

from app.models import Resource


def load(path, store, encoded=False) -> Resource:
    if encoded:
        path = posixpath.normpath(unquote(path))
    if not path.startswith("/safe/"):
        raise PermissionError("resource path is outside the safe namespace")
    return Resource(path=path, body=store.read(path))
