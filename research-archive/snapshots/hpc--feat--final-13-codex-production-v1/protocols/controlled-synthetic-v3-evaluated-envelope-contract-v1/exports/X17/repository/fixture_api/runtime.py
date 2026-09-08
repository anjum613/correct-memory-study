from __future__ import annotations

import copy

class X17Bundles:

    def __init__(self, atomic=False):
        self.atomic = atomic
        self.parts = {'old': {'left': b'old-L', 'right': b'old-R'}}
        self.active = 'old'
        self.observations = []
        self.events = []

    def read(self):
        value = copy.deepcopy(self.parts[self.active])
        self.observations.append((self.active, value))
        return value

    def stage(self, version, name, value):
        self.parts.setdefault(version, {})[name] = bytes(value)
        self.events.append(('stage', version, name))
        if not self.atomic:
            self.read()

    def publish(self, version):
        self.active = version
        self.events.append(('publish', version))
        if not self.atomic:
            self.read()

    def cleanup(self):
        for version in list(self.parts):
            if version != self.active:
                del self.parts[version]
        self.events.append(('cleanup', self.active))

def _x17_stopped(stop_after, point):
    return stop_after == point
