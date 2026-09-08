from __future__ import annotations

import copy

class X20Service:

    def __init__(self):
        self.dispatches = []
        self.writes = []

    def dispatch(self, parsed):
        self.dispatches.append(copy.deepcopy(parsed))
        if parsed['mode'] == 'write':
            self.writes.append('local-write')
        return {'mode': parsed['mode'], 'tags': list(parsed['tags'])}
