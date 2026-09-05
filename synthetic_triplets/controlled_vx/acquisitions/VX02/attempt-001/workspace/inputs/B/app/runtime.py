class Lease:
    def __init__(self, store, key):
        self.store, self.key = store, key
    def __enter__(self):
        self.store.active += 1
        return self
    def __exit__(self, *args):
        self.store.active -= 1
    @property
    def text(self):
        return self.store.values[self.key]
class LeaseStore:
    def __init__(self, values):
        self.values = dict(values)
        self.active = 0
        self.opens = []
    def contains(self, key):
        return key in self.values
    def open(self, key):
        self.opens.append(key)
        return Lease(self, key)
    def replace(self, key, value):
        self.values[key] = value
