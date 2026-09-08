def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        with store.open(slot_id) as record:
            formatted_value = formatter(record.text)
        return lambda: formatted_value
    with store.open(slot_id) as record:
        return formatter(record.text)
