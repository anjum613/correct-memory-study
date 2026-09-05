def render_now(store, key, formatter):
    with store.open(key) as record:
        return formatter(record.text)

def prepare_batch(store, requests, formatter):
    raise NotImplementedError("batch preparation")
