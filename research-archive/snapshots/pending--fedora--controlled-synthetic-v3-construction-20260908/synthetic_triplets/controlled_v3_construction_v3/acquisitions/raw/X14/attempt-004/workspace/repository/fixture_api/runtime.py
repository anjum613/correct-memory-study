from __future__ import annotations

class X14Context:

    def __init__(self):
        self.notifications = []
        self.observations = []
        self.producer_records = ['unchanged']

    def full_references(self):
        return {'notify': lambda value: self.notifications.append(value) or 'ok', 'observe': lambda value: self.observations.append(value) or 'ok', 'maintenance': {'replace': lambda value: self.producer_records.__setitem__(slice(None), [value]) or 'ok'}}

class X14Callback:

    def __init__(self, path, value, raises=False):
        self.path = tuple(path)
        self.value = value
        self.raises = raises
        self.captured = None

    def invoke(self, references):
        self.captured = references
        if self.raises:
            raise RuntimeError('controlled callback failure')
        node = references
        for part in self.path:
            if not isinstance(node, dict) or part not in node:
                return 'denied'
            node = node[part]
        return node(self.value) if callable(node) else 'invalid'

    def invoke_captured(self, path, value):
        node = self.captured
        for part in path:
            if not isinstance(node, dict) or part not in node:
                return 'denied'
            node = node[part]
        return node(value) if callable(node) else 'invalid'
