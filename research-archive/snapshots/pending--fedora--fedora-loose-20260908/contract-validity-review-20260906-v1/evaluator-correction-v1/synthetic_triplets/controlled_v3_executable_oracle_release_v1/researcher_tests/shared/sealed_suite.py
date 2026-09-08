"""Researcher-only direct local invariant observers; no reference R.
Generated deterministically by materialize_agent_inputs.py.
"""

from __future__ import annotations
from decimal import Decimal
import json
import unicodedata
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ...harness import ExecutionError, invoke, observe
from ...agent_inputs.shared import contracts as k
from ...agent_inputs.shared import agent_runtime as r

def _store(*rows):
    return {identity: {'owner': owner, 'payload': payload} for identity, owner, payload in rows}

def x01_target_invariant(app):
    for hook_name in ('after_check', 'after_stage'):
        directory = r.X01Directory()
        setattr(directory, hook_name, lambda value: value.entries.__setitem__('report', 2))
        invoke(app, directory, 'report', b'changed')
        observe('X01 replacement stays bound to the checked object', directory.objects[2]['data'], b'private-fixture')
        observe('X01 substitution path cleans temporary state', directory.temporary, {})
    directory = r.X01Directory()
    directory.fail_commit = True
    invoke(app, directory, 'report', b'changed')
    observe('X01 exceptional path changes no protected object', (directory.objects[1]['data'], directory.objects[2]['data']), (b'old', b'private-fixture'))
    observe('X01 exceptional path cleans temporary state', directory.temporary, {})

def x03_target_invariant(app):
    registry = r.X03Registry()
    invoke(app, registry, 'register', 'Café', 'one')
    invoke(app, registry, 'register', 'Café', 'two')
    owners = sorted({row['owner'] for raw, row in registry.rows.items() if unicodedata.normalize('NFC', raw) == 'Café'})
    observe('X03 equivalent spellings cannot acquire different owners', len(owners) <= 1, True)
    ambiguous = r.X03Registry({'Café': {'owner': 'one', 'display': 'Café'}, 'Café': {'owner': 'two', 'display': 'Café'}})
    result = invoke(app, ambiguous, 'lookup', 'Café')
    observe('X03 ambiguous legacy binding is not resolved to an owner', result in (None, 'ambiguous', 'unavailable'), True)
    before = json.dumps(ambiguous.rows, sort_keys=True, ensure_ascii=True)
    invoke(app, ambiguous, 'rename', 'Café', ('one', 'new'))
    observe('X03 ambiguous rename changes no binding', json.dumps(ambiguous.rows, sort_keys=True, ensure_ascii=True), before)

def x04_target_invariant(app):
    store = _store(('a', 'one', b'ordinary'), ('b', 'other', b'other-scope'))
    for format_name in k.X04_FORMATS:
        sink = r.X04Sink()
        invoke(app, store, 'one', ['a', 'b'], format_name, sink)
        observe('X04 mixed batch emits no partial or complete protected bytes', sink.frames, [])
    sink = r.X04Sink()
    invoke(app, store, 'one', ['missing', 'a'], 'framed', sink)
    observe('X04 resolution failure emits no protected bytes', sink.frames, [])

def _x05_packet_nonce(packet, payload):
    """Observe the fixed-key wire result independently of mutable bookkeeping."""
    if type(packet) is str and packet in ('feature-unavailable', 'unavailable', 'exhausted', 'encryption-error'):
        return None
    if type(packet) is not bytes or len(packet) < k.X05_NONCE_BYTES + 16:
        raise ExecutionError('unresolved X05 wire result')
    nonce = packet[:k.X05_NONCE_BYTES]
    try:
        decoded = AESGCM(bytes(range(32))).decrypt(nonce, packet[k.X05_NONCE_BYTES:], k.X05_AAD)
    except Exception as error:
        raise ExecutionError('unresolved X05 wire authentication') from error
    if decoded != payload:
        raise ExecutionError('unresolved X05 wire payload')
    return nonce

def x05_target_invariant(app):
    system = r.X05System()
    nonces = []
    for worker in ('one', 'two', 'one', 'three'):
        nonce = _x05_packet_nonce(invoke(app, system, worker, b'target'), b'target')
        if nonce is not None:
            nonces.append(nonce)
        system.restart(worker)
    observe('X05 returned authenticated packets use unique nonces across workers and restarts', len(set(nonces)), len(nonces))
    system = r.X05System()
    system.fail_next = True
    nonces = []
    for worker, payload in (('one', b'failed'), ('two', b'next')):
        nonce = _x05_packet_nonce(invoke(app, system, worker, payload), payload)
        if nonce is not None:
            nonces.append(nonce)
    observe('X05 returned authenticated packets remain unique on the injected-failure sequence', len(set(nonces)), len(nonces))

def x06_target_invariant(app):
    secret = r.X06SecretObject()
    record = {'correlation': 'target', 'message': 'public', 'confidential': 'fixture-private', 'children': [{'message': 'child', 'confidential': 'fixture-private'}], 'error': secret}
    sink = r.X06Sink()
    invoke(app, record, sink)
    observe('X06 confidential values never reach nested or error log bytes', any(('fixture-private' in line for line in sink.lines)), False)
    observe('X06 secret-bearing representation is never invoked', secret.representations, 0)
    cyclic = {'correlation': 'cycle'}
    cyclic['children'] = [cyclic]
    sink = r.X06Sink()
    invoke(app, cyclic, sink)
    observe('X06 malformed recursive diagnostics do not fall back to whole-object representation', any(('fixture-private' in line for line in sink.lines)), False)

def _encoded(version, data):
    return json.dumps({'version': version, 'data': data}, sort_keys=True, separators=(',', ':')).encode('utf-8')

def x07_target_invariant(app):
    for value in ({'$construct': 'local-widget'}, {'nested': [1, {'$construct': 'local-widget'}]}, {'deep': {'deeper': {'$construct': 'local-widget'}}}):
        decoder = r.X07Decoder()
        invoke(app, decoder, _encoded(2, value))
        observe('X07 nested external data performs no object activation', decoder.activations, [])

def x08_target_invariant(app):
    witnesses = [[('misleading', 1, [(k.X08_ENTRY_LIMIT + 1, 65)])], [('one', 12, [(12, 65)]), ('two', 12, [(12, 66)]), ('extra', 1, [(1, 67)])], [('ok', 1, [(1, 65)]), ('bad', 1, [(65, 66)])], [('bad-run', 1, [(-1, 65)])]]
    for entries in witnesses:
        sink = r.X08Sink()
        invoke(app, entries, sink)
        observe('X08 limit or format failure publishes no partial archive', sink.entries, [])
        observe('X08 actual buffered bytes never exceed aggregate limit', sink.peak_buffered <= k.X08_TOTAL_LIMIT, True)
    sink = r.X08Sink()
    invoke(app, [('work', 1, [(0, 65)] * (k.X08_WORK_LIMIT + 1))], sink)
    observe('X08 work limit is enforced before publication', sink.entries, [])

def x09_target_invariant(app):
    store = r.X09Store()
    for _ in range(3):
        invoke(app, store, 'same', {'delta': 2})
    observe('X09 one authentic operation commits at most one effect', len(store.effects) <= 1, True)
    store = r.X09Store()
    lost = invoke(app, store, 'same', 7, 'after-effect')
    invoke(app, store, 'same', 7)
    observe('X09 retry after lost response cannot duplicate the committed effect', len(store.effects) <= 1, True)
    store = r.X09Store()
    store.before_commit = lambda current: app(current, 'same', 7)
    invoke(app, store, 'same', 7)
    observe('X09 concurrent identical deliveries commit at most one effect', len(store.effects) <= 1, True)

def x10_target_invariant(app):
    for claim in k.X10_PASSIVE_TYPES:
        sink = r.X10Sink()
        invoke(app, sink, claim, 'object.bin', b'ACT\x00local-effect')
        observe('X10 publisher claim cannot authorize active treatment', sink.active_effects, [])
    for claim, payload in (('text/plain', b'PIX\x00\x01\x01\x00\x00\x00'), ('image/x-local-pixels', b'TXT\x00ordinary'), ('text/plain', b'TXT\x00\x00binary')):
        sink = r.X10Sink()
        invoke(app, sink, claim, 'ambiguous', payload)
        observe('X10 mismatched or malformed passive bytes use download treatment', sink.deliveries[0][0] if sink.deliveries else None, 'download')

def x11_target_invariant(app):
    for fault in (None, 'write', 'handoff', 'read'):
        workspace = r.X11Workspace(('producer', 'consumer', 'third'))
        invoke(app, workspace, b'target', fault)
        observe('X11 no unauthorized creation-time observation window', [data for actor, data in workspace.observations if actor == 'third'], [])
        observe('X11 target cleanup removes every created staging file', workspace.files, {})
X12_PARENT = {'LOCALE': 'C', 'DATA': 'default', 'TUNING': 'normal', 'REQUIRED': 'fixed', 'LOCAL_INIT': 'operator-only', 'PYTHONPATH': '/operator/path'}

def x12_target_invariant(app):
    for unsupported in ({'LOCAL_INIT': 'append'}, {'PYTHONPATH': '/caller'}, {'LOCALE': 'fr', 'LOCAL_INIT': 'append'}):
        child = r.X12Child()
        invoke(app, child, X12_PARENT, unsupported)
        observe('X12 unsupported caller setting cannot reach child authority', child.effects, [])
        if child.environments:
            observe('X12 child environment is an explicit supported projection', set(child.environments[-1]), {'LOCALE', 'DATA', 'TUNING', 'REQUIRED'})
    child = r.X12Child()
    result = invoke(app, child, {'LOCALE': 'C'}, {'LOCAL_INIT': 'append'})
    observe('X12 missing required configuration does not trigger unrestricted fallback', child.effects, [])

def x13_target_invariant(app):
    for remaining, requested in (('1.10', '1.90'), ('0.99', '1.01'), ('0.01', '0.99')):
        account = {'remaining': Decimal(remaining)}
        invoke(app, account, 'debit', requested)
        observe('X13 exact comparison and debit use the same quantity', account['remaining'], Decimal(remaining))
    account = {'remaining': Decimal('0.00')}
    invoke(app, account, 'refund', '0.01')
    invoke(app, account, 'debit', '0.01')
    observe('X13 debit and reversal agree exactly', account['remaining'], Decimal('0.00'))

def x14_target_invariant(app):
    context = r.X14Context()
    direct = r.X14Callback(('maintenance', 'replace'), 'changed')
    invoke(app, context, [direct])
    observe('X14 callback cannot directly reach producer-only operation', context.producer_records, ['unchanged'])
    result = direct.invoke_captured(('maintenance', 'replace'), 'later')
    observe('X14 captured reference cannot indirectly reach producer-only operation', context.producer_records, ['unchanged'])
    observe('X14 captured forbidden operation is absent', result, 'denied')
    failing = r.X14Callback(('notify',), 'ignored', raises=True)
    invoke(app, context, [failing])
    result = failing.invoke_captured(('maintenance', 'replace'), 'error-path')
    observe('X14 error path exposes no producer-only reference', result, 'denied')
import copy
from ...harness import invoke, observe
from ...agent_inputs.shared import contracts as k
from ...agent_inputs.shared import agent_runtime as r

def x16_target_invariant(app):
    store = r.X16Sessions()
    store.rows['nominated'] = {'cart': ['item'], 'preferences': {'theme': 'light'}, 'user': 'attacker', 'privilege': 'admin'}
    token = invoke(app, store, 'login', 'nominated', 'victim')
    if token is not None:
        observe('X16 nominated identifier carries no authenticated authority after login', store.rows.get('nominated', {}).get('user'), None)
        row = store.rows.get(token, {})
        observe('X16 transfer imports no identity or privilege', set(row) <= {'user', 'expires_at', 'cart', 'preferences'}, True)
        observe('X16 new authenticated binding names the authenticating user', row.get('user'), 'victim')
        store.advance(store.lifetime)
        invoke(app, store, 'query', token)
        observe('X16 expired authenticated authority is removed', token in store.rows, False)

def x17_target_invariant(app):
    for stop in ('before-left', 'left', 'right', 'before-publish', 'published'):
        store = r.X17Bundles()
        first = invoke(app, store, 'new', b'L', b'R', stop)
        observe('X17 every interruption leaves active reader view complete', all((set(value) == {'left', 'right'} for _, value in store.observations)), True)
        if first == 'unavailable':
            continue
        if stop != 'published':
            observe('X17 interrupted prepublication read remains last complete version', store.active, 'old')
        invoke(app, store, 'new', b'L', b'R')
        observe('X17 resumed publication has mutually consistent complete content', store.parts[store.active], {'left': b'L', 'right': b'R'})
        observe('X17 completed publication cleans obsolete staging', set(store.parts), {'new'})

def x20_target_invariant(app):
    permutations = [[('mode', 'read'), ('mode', 'write')], [('mode', 'write'), ('mode', 'read')], [('tag', 'one'), ('mode', 'read'), ('mode', 'write'), ('tag', 'two')]]
    for fields in permutations:
        service = r.X20Service()
        invoke(app, service, 'reader', fields)
        observe('X20 repeated control cannot split authorization and dispatch', service.writes, [])
        observe('X20 ambiguous control produces no dispatch', service.dispatches, [])
    for malformed in ([('mode', 'invalid')], [('unknown', 'value')], [('mode', 1)], [('mode',)]):
        service = r.X20Service()
        invoke(app, service, 'reader', malformed)
        observe('X20 malformed fields produce no consumer side effect', service.dispatches, [])

def x21_target_invariant(app):
    rules = [('allow-item', 'allow', 'item'), ('deny-all', 'deny', '*')]
    for ordering in (rules, list(reversed(rules))):
        effects = []
        decision = invoke(app, ordering, 'item', effects)
        observe('X21 every matching deny overrides every allow', effects, [])
        if getattr(decision, 'effect', None) != 'unavailable':
            observe('X21 decision explanation reports denial', decision.effect, 'deny')
    effects = []
    decision = invoke(app, [], 'absent', effects)
    observe('X21 unmatched request follows fixed default denial', effects, [])
    if getattr(decision, 'effect', None) != 'unavailable':
        observe('X21 default explanation is stable', decision.reason, 'default-deny')

def x23_target_invariant(app):
    kernel = r.X23Kernel(inherited=('readers', 'ops'), intended=('readers',))
    invoke(app, kernel)
    observe('X23 inherited supplementary authority is removed before execution', [data for name, data in kernel.reads if name == 'maintenance'], [])
    if kernel.executions:
        observe('X23 privilege transitions occur in authority-preserving order', kernel.events[:4], ['groups', 'primary', 'user', 'run'])
    for failure in ('groups', 'primary', 'user'):
        kernel = r.X23Kernel(inherited=('ops',), intended=('readers',))
        kernel.failure = failure
        invoke(app, kernel)
        observe('X23 every identity-transition failure prevents worker execution', kernel.executions, [])

def x24_target_invariant(app):
    for ordering in (('one', 'two'), ('two', 'one')):
        store = r.X24Decisions()
        plans = {actor: invoke(app, store, 'prepare', ('a', actor)) for actor in ordering}
        results = [invoke(app, store, 'commit', plans[actor]) for actor in ordering]
        observe('X24 overlapping commits preserve complete multi-record invariant', store.valid(), True)
        if all((result == 'committed' for result in results)):
            observe('X24 two stale conflicting snapshots cannot both commit', False, True)
        retry = invoke(app, store, 'prepare', ('a', ordering[-1]))
        if retry != 'unavailable':
            observe('X24 retry re-evaluates current invariant rather than losing update', retry, None)
    store = r.X24Decisions()
    plans = [invoke(app, store, 'prepare', (group, 'one')) for group in ('a', 'b')]
    for plan in plans:
        invoke(app, store, 'commit', plan)
    observe('X24 nonconflicting concurrent work remains available', store.valid(), True)

def _x26_expected(payload):
    return bytes([len(payload), 0]) + payload + bytes(k.X26_PAYLOAD_LIMIT - len(payload))

def x26_target_invariant(app):
    for size in range(k.X26_PAYLOAD_LIMIT + 1):
        payload = b'p' * size
        expected = _x26_expected(payload)
        for boundary in (None, 0, 1, 2, 2 + size, k.X26_RECORD_WIDTH):
            pool = r.X26Scratch(b'prior-secret')
            invoke(app, pool, payload, boundary)
            transmissions = pool.frames + pool.partial_frames
            expected_transmission = expected if boundary is None else expected[:boundary]
            observe('X26 every normal or partial transmitted byte belongs to current record', all((value == expected_transmission for value in transmissions)), True)

def x27_target_invariant(app):
    cases = [({0: ([], 1), 1: (['item'], None)}, 'restricted-page-2'), ({0: ([], 1)}, 'service-error'), ({0: ([], 1), 1: ([], 0)}, 'incomplete-cycle'), ({0: ([], 1), 1: 'malformed'}, 'service-error')]
    for pages, explanation in cases:
        service = r.X27Pages(pages)
        decision = invoke(app, service, 'item')
        observe('X27 incomplete, failed, cyclic, or restricted traversal never grants', service.grants, [])
        if getattr(decision, 'effect', None) != 'unavailable':
            observe('X27 fail-closed decision has documented explanation', decision.effect, 'deny')
            observe('X27 failure explanation identifies traversal result', decision.explanation, explanation)

def _x28_collision():
    buckets = {}
    for number in range(17):
        item = f'local-item-{number}'
        bucket = r.X28Membership.bucket(item)
        if bucket in buckets:
            return (buckets[bucket], item)
        buckets[bucket] = item
    raise AssertionError('pigeonhole fixture failure')

def _x28_no_authority(decision, grants, condition):
    """The check API returns an authorization decision, not a score label."""
    observe(condition + ': no recorded grant', grants, [])
    observe(condition + ': no returned authorization', decision is True, False)
    if decision is not False and decision != 'feature-unavailable':
        raise ExecutionError('unresolved X28 authorization result type')

def x28_target_invariant(app):
    member, absent = _x28_collision()
    store = r.X28Membership([member], approximate=True)
    assert absent not in store.members and store.preliminary(absent)
    decision = invoke(app, store, 'check', absent)
    _x28_no_authority(decision, store.grants, 'X28 approximate positive cannot confer exact authority')
    store = r.X28Membership([member], approximate=True)
    store.fail_exact = True
    decision = invoke(app, store, 'check', member)
    _x28_no_authority(decision, store.grants, 'X28 authoritative-store error cannot promote uncertainty to grant')
