def render(store, slot_id: str, formatter, defer: bool = False):
    def _render_record():
        with store.open(slot_id) as record:
            return formatter(record.text)

    if defer:
        return _render_record
    return _render_record()
