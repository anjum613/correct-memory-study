from __future__ import annotations

class X11Workspace:

    def __init__(self, default_readers=('producer', 'consumer')):
        self.default_readers = set(default_readers)
        self.files = {}
        self.observations = []
        self.events = []
        self.next_id = 1

    def create(self, allowed, content):
        identity = self.next_id
        self.next_id += 1
        self.files[identity] = [set(allowed), bytes(content)]
        self.events.append(('create', identity, frozenset(allowed)))
        self._observe(identity)
        return identity

    def permissions(self, identity, allowed):
        self.files[identity][0] = set(allowed)
        self.events.append(('permissions', identity, frozenset(allowed)))
        self._observe(identity)

    def _observe(self, identity):
        allowed, content = self.files[identity]
        for actor in sorted(allowed):
            self.observations.append((actor, content))

    def read(self, identity, actor, fault=None):
        if fault == 'read':
            raise OSError('controlled read failure')
        allowed, content = self.files[identity]
        return content if actor in allowed else None

    def remove(self, identity):
        self.files.pop(identity, None)
        self.events.append(('remove', identity))
