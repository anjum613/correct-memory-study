def render(store, slot_id: str, formatter, defer: bool = False):
    with store.open(slot_id) as record:
        text = record.text

    if defer:
        return lambda: formatter(text)

    return formatter(text)
