from __future__ import annotations

from decimal import Decimal
from fixture_api.public_harness import invoke
from fixture_api import contracts as k

def x13_existing(app):
    account = {'remaining': Decimal('5.00')}
    assert invoke(app, account, 'debit', '2') == '3.00'
    assert invoke(app, account, 'refund', '1') == '4.00'
    assert invoke(app, account, 'debit', '0') == '4.00'

def x13_feature(app):
    account = {'remaining': Decimal('5.00')}
    assert invoke(app, account, 'debit', '1.25') == '3.75'
    assert invoke(app, account, 'refund', '0.50') == '4.25'
    assert invoke(app, account, 'debit', '4.25') == '0.00'
    for invalid in ('0.001', '-1.00', 'NaN', 'Infinity', '1000000.01', 'not-a-number'):
        before = account['remaining']
        assert invoke(app, account, 'debit', invalid) == 'invalid'
        assert account['remaining'] == before
    maximum = {'remaining': Decimal(k.X13_MAX_UNITS)}
    assert invoke(app, maximum, 'refund', '0.01') == 'invalid'
