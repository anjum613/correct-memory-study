def render(store, slot_id: str, formatter, defer: bool = False):
    def format_record():
        with store.open(slot_id) as record:
            return formatter(record.text)

    if defer:
        return format_record
    return format_record()
