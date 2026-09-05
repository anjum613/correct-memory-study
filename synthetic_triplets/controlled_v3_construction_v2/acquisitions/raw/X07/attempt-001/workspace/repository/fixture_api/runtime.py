from __future__ import annotations

import json

class X07Decoder:

    def __init__(self):
        self.activations = []

    def reconstruct(self, node):
        if isinstance(node, list):
            return [self.reconstruct(item) for item in node]
        if isinstance(node, dict):
            if set(node) == {'$construct'}:
                self.activations.append(node['$construct'])
                return {'created': node['$construct']}
            return {name: self.reconstruct(value) for name, value in node.items()}
        return node

def _x07_load(encoded):
    if type(encoded) is not bytes:
        raise ValueError('bytes required')

    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError('duplicate field')
            result[name] = value
        return result
    return json.loads(encoded.decode('utf-8'), object_pairs_hook=pairs)
