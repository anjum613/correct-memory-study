def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        def render_deferred():
            with store.open(slot_id) as record:
                return formatter(record.text)

        return render_deferred
    with store.open(slot_id) as record:
        return formatter(record.text)
