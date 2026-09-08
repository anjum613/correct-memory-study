def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        def deferred():
            with store.open(slot_id) as record:
                return formatter(record.text)

        return deferred
    with store.open(slot_id) as record:
        return formatter(record.text)
