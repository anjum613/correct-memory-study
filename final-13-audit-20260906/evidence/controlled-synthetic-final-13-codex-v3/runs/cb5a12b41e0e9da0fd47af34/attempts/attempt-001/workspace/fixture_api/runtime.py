from __future__ import annotations

import copy

class X24Decisions:

    def __init__(self):
        self.rows = {'a': {'one': True, 'two': True}, 'b': {'one': True, 'two': True}}
        self.revisions = {'a': 0, 'b': 0}
        self.events = []

    def valid(self):
        return all((any(row.values()) for row in self.rows.values()))

    def commit(self, group, actor):
        self.rows[group][actor] = False
        self.revisions[group] += 1
        self.events.append(('commit', group, actor))

def _x24_read(store, group):
    return copy.deepcopy(store.rows[group])

def _x24_prepare(store, value):
    group, actor = value
    if group not in store.rows or actor not in store.rows[group] or (not store.rows[group][actor]):
        return None
    if not any((active for other, active in store.rows[group].items() if other != actor)):
        return None
    return (group, actor, store.revisions[group])
