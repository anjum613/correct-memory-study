"""Baseline access to the last complete active bundle."""


def run(bundle_store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return bundle_store.read()
    raise NotImplementedError("Resumable publication is unavailable")
