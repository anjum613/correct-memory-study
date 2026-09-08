def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        with store.open(slot_id) as record:
            formatted = formatter(record.text)
        return lambda: formatted
    with store.open(slot_id) as record:
        return formatter(record.text)
