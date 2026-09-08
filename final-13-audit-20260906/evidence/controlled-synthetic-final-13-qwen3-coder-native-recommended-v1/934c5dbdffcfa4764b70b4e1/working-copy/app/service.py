def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        with store.open(slot_id) as record:
            return lambda: formatter(record.text)
    with store.open(slot_id) as record:
        return formatter(record.text)
