from app.models import Resource


def load(path, store, encoded=False) -> Resource:
    if encoded:
        raise NotImplementedError("encoded resource paths are not supported")
    if not path.startswith("/safe/"):
        raise PermissionError("resource path is outside the safe namespace")
    return Resource(path=path, body=store.read(path))
