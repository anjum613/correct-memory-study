def render_batch_now(store, requests, formatter):
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
    results = []
    for ordinal, (key, prefix, suffix) in enumerate(prepared):
        with store.open(key) as record:
            text = prefix + formatter(record.text) + suffix
            results.append({"id": key, "text": text, "ordinal": ordinal})
    return results
