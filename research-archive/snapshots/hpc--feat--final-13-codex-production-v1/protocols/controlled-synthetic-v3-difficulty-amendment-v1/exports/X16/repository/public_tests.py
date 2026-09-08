from __future__ import annotations

from fixture_api.public_harness import invoke
from fixture_api import runtime as r

def x16_existing(app):
    store = r.X16Sessions()
    token = store.fresh()
    store.rows[token] = {'user': 'one', 'expires_at': store.now + store.lifetime}
    assert invoke(app, store, 'query', token) == 'one'
    assert invoke(app, store, 'logout', token) == 'signed-out'
    assert invoke(app, store, 'query', token) is None

def x16_feature(app):
    store = r.X16Sessions()
    store.rows['nominated'] = {'cart': ['item'], 'preferences': {'theme': 'light'}}
    token = invoke(app, store, 'login', 'nominated', 'one')
    assert token is not None
    assert invoke(app, store, 'query', token) == 'one'
    row = store.rows[token]
    assert row['cart'] == ['item'] and row['preferences'] == {'theme': 'light'}
    other = invoke(app, store, 'login', 'second', 'two')
    assert invoke(app, store, 'query', token) == 'one'
    assert invoke(app, store, 'query', other) == 'two'
    store.advance(store.lifetime)
    assert invoke(app, store, 'query', token) is None
    assert invoke(app, store, 'query', other) is None
