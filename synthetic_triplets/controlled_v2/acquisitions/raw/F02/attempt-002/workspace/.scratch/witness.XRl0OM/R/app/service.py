def render(store, slot_id: str, formatter, defer=False):
    with store.open(slot_id) as record:
        if defer:
            text = record.text
            return lambda: formatter(text)
        return formatter(record.text)
