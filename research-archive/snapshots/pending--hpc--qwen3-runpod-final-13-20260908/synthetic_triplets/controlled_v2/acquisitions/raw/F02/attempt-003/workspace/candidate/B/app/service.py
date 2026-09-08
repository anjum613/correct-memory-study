def render(store, slot_id: str, formatter):
    with store.open(slot_id) as record:
        return formatter(record.text)
