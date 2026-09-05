class Repository:
    def __init__(self, bodies):
        self.bodies = dict(bodies)
        self.reads = []
    def read(self, user, key):
        self.reads.append((user, key))
        return self.bodies[(user, key)]
