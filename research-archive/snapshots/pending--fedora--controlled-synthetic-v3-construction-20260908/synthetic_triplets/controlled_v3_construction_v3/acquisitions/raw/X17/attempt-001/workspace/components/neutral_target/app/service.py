"""Read the existing complete bundle; staged publication is unavailable."""


def run(bundle_store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return bundle_store.read()
    raise NotImplementedError("Resumable publication is unavailable")
