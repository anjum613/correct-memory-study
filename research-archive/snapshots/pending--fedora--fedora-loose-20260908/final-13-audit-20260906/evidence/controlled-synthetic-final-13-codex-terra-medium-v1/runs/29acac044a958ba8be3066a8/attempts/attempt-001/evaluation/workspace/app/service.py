def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        def deferred_render():
            with store.open(slot_id) as record:
                return formatter(record.text)

        return deferred_render
    with store.open(slot_id) as record:
        return formatter(record.text)
