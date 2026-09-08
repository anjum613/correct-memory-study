def render(store, slot_id: str, formatter, defer: bool = False):
    with store.open(slot_id) as record:
        if defer:
            return lambda: formatter(record.text)
        return formatter(record.text)
