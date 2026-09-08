from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import crypto as c

def x22_existing(app):
    for bits, key_class, suite in ((2048, 'P', 'PS256'), (3072, 'C', 'RS256')):
        consumer = []
        slot, fields = c.fixed_x22_fields(bits, key_class, suite, 1, 'empty')
        assert invoke(app, slot, fields, consumer) == 'accepted' and consumer == [b'']

def x22_feature(app):
    for bits in (2048, 3072):
        for key_class, suite in (('P', 'PS256'), ('C', 'RS256')):
            for version, payload_id in ((1, 'ordinary'), (2, 'max')):
                consumer = []
                slot, fields = c.fixed_x22_fields(bits, key_class, suite, version, payload_id)
                assert invoke(app, slot, fields, consumer) == 'accepted'
                assert consumer == [bytes.fromhex(c.VECTORS['payloads'][payload_id])]
