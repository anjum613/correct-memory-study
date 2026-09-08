def render(store, slot_id: str, formatter, defer: bool = False):
    if defer:
        return lambda: _do_format(store, slot_id, formatter)
    else:
        return _do_format(store, slot_id, formatter)


def _do_format(store, slot_id: str, formatter):
    with store.open(slot_id) as record:
        return formatter(record.text)
