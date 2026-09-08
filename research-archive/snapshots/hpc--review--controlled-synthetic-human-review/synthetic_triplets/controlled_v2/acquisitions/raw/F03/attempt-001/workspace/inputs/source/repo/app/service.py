from app.models import Resource


def load_canonical(path, store) -> Resource:
    if not path.value.startswith("/safe/"):
        raise PermissionError("resource path is outside the safe namespace")
    return Resource(path=path.value, body=store.read(path.value))
