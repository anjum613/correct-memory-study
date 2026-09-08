def render(store, slot_id: str, formatter, defer: bool = False):
    def _render():
        with store.open(slot_id) as record:
            return formatter(record.text)

    if defer:
        return _render

    return _render()
