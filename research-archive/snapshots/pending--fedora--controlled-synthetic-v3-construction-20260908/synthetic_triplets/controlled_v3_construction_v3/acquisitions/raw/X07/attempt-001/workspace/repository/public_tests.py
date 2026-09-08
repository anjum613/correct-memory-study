from __future__ import annotations
import json
from fixture_api.public_harness import invoke
from fixture_api import contracts as k
from fixture_api import runtime as r

def _encoded(version, data):
    return json.dumps({'version': version, 'data': data}, sort_keys=True, separators=(',', ':')).encode('utf-8')

def x07_existing(app):
    decoder = r.X07Decoder()
    assert invoke(app, decoder, _encoded(1, 'ordinary')) == ('ok', 'ordinary')

def x07_feature(app):
    values = ['legacy', {'job': 'ordinary', 'options': [1, None, True, {'name': 'nested'}]}]
    for version in k.X07_VERSIONS:
        for value in values:
            decoder = r.X07Decoder()
            assert invoke(app, decoder, _encoded(version, value)) == ('ok', value)
    invalid = [b'{}', b'{"version":3,"data":1}', b'{"version":1,"version":2,"data":1}', b'not-json', _encoded(2, [[[[['too-deep']]]]])]
    for value in invalid:
        assert invoke(app, r.X07Decoder(), value)[0] == 'invalid'
