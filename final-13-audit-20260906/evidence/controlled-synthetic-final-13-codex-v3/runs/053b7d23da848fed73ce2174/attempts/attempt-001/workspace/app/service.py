def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        with store.open(slot_id) as record:
            value = record.text

        def callback():
            return formatter(value)

        return callback
    with store.open(slot_id) as record:
        return formatter(record.text)
