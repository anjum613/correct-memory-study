class Lease:
    def __init__(self, store, slot_id):
        self._store = store
        self._slot_id = slot_id
        self.closed = False

    @property
    def text(self):
        return self._store.slots[self._slot_id]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True


class LeaseStore:
    def __init__(self, slots):
        self.slots = dict(slots)

    def open(self, slot_id):
        return Lease(self, slot_id)

    def replace(self, slot_id, text):
        self.slots[slot_id] = text
