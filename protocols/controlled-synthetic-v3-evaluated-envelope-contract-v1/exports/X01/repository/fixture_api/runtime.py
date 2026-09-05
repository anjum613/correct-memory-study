from __future__ import annotations

class X01Directory:

    def __init__(self):
        self.entries = {'report': 1, 'other': 2}
        self.objects = {1: {'owner': 'writer', 'data': b'old'}, 2: {'owner': 'other', 'data': b'private-fixture'}}
        self.temporary = {}
        self.events = []
        self.next_temporary = 1
        self.after_check = None
        self.after_stage = None
        self.fail_stage = False
        self.fail_commit = False

    def lookup(self, name):
        return self.entries.get(name)

    def attributes(self, identity):
        return dict(self.objects[identity])

    def hook(self, name):
        callback = getattr(self, name)
        if callback is not None:
            callback(self)

    def stage(self, data):
        if self.fail_stage:
            raise OSError('controlled staging failure')
        identity = self.next_temporary
        self.next_temporary += 1
        self.temporary[identity] = bytes(data)
        self.events.append(('stage', identity))
        return identity

    def discard(self, identity):
        self.temporary.pop(identity, None)
        self.events.append(('cleanup', identity))

    def replace_path(self, name, temporary):
        if self.fail_commit:
            raise OSError('controlled replacement failure')
        identity = self.lookup(name)
        self.objects[identity]['data'] = self.temporary[temporary]
        self.events.append(('replace', identity))
