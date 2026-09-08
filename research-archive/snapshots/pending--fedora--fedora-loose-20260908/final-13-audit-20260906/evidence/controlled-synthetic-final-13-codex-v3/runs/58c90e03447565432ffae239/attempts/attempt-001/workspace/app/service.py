def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        def render_later():
            with store.open(slot_id) as record:
                return formatter(record.text)

        return render_later
    with store.open(slot_id) as record:
        return formatter(record.text)
