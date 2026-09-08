def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        def callback():
            with store.open(slot_id) as record:
                return formatter(record.text)

        return callback
    with store.open(slot_id) as record:
        return formatter(record.text)
