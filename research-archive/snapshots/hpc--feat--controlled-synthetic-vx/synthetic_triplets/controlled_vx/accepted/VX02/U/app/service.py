from app.operations import make_callback


def render_now(store, key, formatter):
    with store.open(key) as record:
        return formatter(record.text)

def prepare_batch(store, requests, formatter):
    prepared = []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("request must be a mapping")
        key = request.get("id")
        prefix = request.get("prefix")
        suffix = request.get("suffix")
        if not isinstance(key, str) or not key or not store.contains(key):
            raise ValueError("unknown record")
        if not isinstance(prefix, str) or not isinstance(suffix, str):
            raise ValueError("decoration must be text")
        prepared.append((key, prefix, suffix))

    callbacks = []
    for ordinal, (key, prefix, suffix) in enumerate(prepared):
        with store.open(key) as record:
            callbacks.append(
                make_callback(key, prefix, suffix, ordinal, record, formatter)
            )
    return callbacks
