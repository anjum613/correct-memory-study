def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        with store.open(slot_id) as record:
            text = record.text

        def callback():
            return formatter(text)

        return callback

    with store.open(slot_id) as record:
        return formatter(record.text)
