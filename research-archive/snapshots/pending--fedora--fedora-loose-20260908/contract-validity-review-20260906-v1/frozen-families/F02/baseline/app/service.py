def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        raise NotImplementedError("deferred rendering is not implemented")
    with store.open(slot_id) as record:
        return formatter(record.text)
