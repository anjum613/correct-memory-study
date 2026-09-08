"""Source-only local fixture runtime; contains no B or secure R implementation.
Generated deterministically by materialize_agent_inputs.py.
"""

from __future__ import annotations
import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import unicodedata
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from . import contracts as k

class X01Directory:

    def __init__(self):
        self.entries = {'report': 1, 'other': 2}
        self.objects = {1: {'owner': 'writer', 'data': b'old'}, 2: {'owner': 'other', 'data': b'private-fixture'}}
        self.temporary = {}
        self.events = []
        self.next_temporary = 1
        self.after_check = None
        self.after_stage = None
        self.fail_stage = False
        self.fail_commit = False

    def lookup(self, name):
        return self.entries.get(name)

    def attributes(self, identity):
        return dict(self.objects[identity])

    def hook(self, name):
        callback = getattr(self, name)
        if callback is not None:
            callback(self)

    def stage(self, data):
        if self.fail_stage:
            raise OSError('controlled staging failure')
        identity = self.next_temporary
        self.next_temporary += 1
        self.temporary[identity] = bytes(data)
        self.events.append(('stage', identity))
        return identity

    def discard(self, identity):
        self.temporary.pop(identity, None)
        self.events.append(('cleanup', identity))

    def replace_path(self, name, temporary):
        if self.fail_commit:
            raise OSError('controlled replacement failure')
        identity = self.lookup(name)
        self.objects[identity]['data'] = self.temporary[temporary]
        self.events.append(('replace', identity))

def x01_source(directory, name, data):
    identity = directory.lookup(name)
    if identity is None:
        return 'missing'
    if directory.attributes(identity)['owner'] != 'writer':
        return 'denied'
    temporary = None
    try:
        directory.hook('after_check')
        temporary = directory.stage(data)
        directory.hook('after_stage')
        directory.replace_path(name, temporary)
        return 'updated'
    except OSError:
        return 'error'
    finally:
        if temporary is not None:
            directory.discard(temporary)

def _x03_valid(handle):
    if not isinstance(handle, str) or not k.X03_MIN_LENGTH <= len(handle) <= k.X03_MAX_LENGTH:
        return False
    return all((character == '_' or character == '-' or unicodedata.category(character)[0] in {'L', 'M', 'N'} for character in handle))

def _x03_key(handle):
    return unicodedata.normalize('NFC', handle)

class X03Registry:

    def __init__(self, rows=None):
        self.rows = dict(rows or {})

def _x03_raw(registry, operation, handle, argument=None):
    if not _x03_valid(handle):
        return 'invalid'
    if operation == 'lookup':
        return registry.rows.get(handle, {}).get('owner')
    if operation == 'register':
        if handle in registry.rows:
            return 'collision'
        registry.rows[handle] = {'owner': argument, 'display': handle}
        return 'registered'
    if operation == 'rename':
        if not isinstance(argument, tuple) or len(argument) != 2:
            return 'invalid'
        actor, new = argument
        if not _x03_valid(new):
            return 'invalid'
        if registry.rows.get(handle, {}).get('owner') != actor:
            return 'denied'
        if new in registry.rows and new != handle:
            return 'collision'
        row = registry.rows.pop(handle)
        row['display'] = new
        registry.rows[new] = row
        return 'renamed'
    return 'invalid'

def x03_source(registry, operation, handle, argument=None):
    return _x03_raw(registry, operation, handle, argument)

class X04Sink:

    def __init__(self, fail=False):
        self.frames = []
        self.fail = fail

    def emit(self, data):
        if self.fail:
            raise OSError('controlled sink failure')
        self.frames.append(bytes(data))

def _x04_encode(rows, format_name):
    if format_name == 'framed':
        output = bytearray()
        for identity, payload in rows:
            name = identity.encode('ascii')
            output += len(name).to_bytes(1, 'big') + name
            output += len(payload).to_bytes(2, 'big') + payload
        return bytes(output)
    if format_name == 'json-lines':
        return b''.join((json.dumps({'id': identity, 'payload_hex': payload.hex()}, sort_keys=True, separators=(',', ':')).encode('ascii') + b'\n' for identity, payload in rows))
    raise ValueError('unsupported format')

def x04_source(store, principal, selected, format_name, sink):
    if format_name not in k.X04_FORMATS or not isinstance(selected, (list, tuple)):
        return 'invalid'
    identities = list(dict.fromkeys(selected))
    if len(identities) > k.X04_MAX_RECORDS or any((not isinstance(value, str) for value in identities)):
        return 'invalid'
    if any((identity not in store for identity in identities)):
        return 'missing'
    if identities and store[identities[0]]['owner'] != principal:
        return 'denied'
    rows = [(identity, bytes(store[identity]['payload'])) for identity in identities]
    try:
        sink.emit(_x04_encode(rows, format_name))
    except (OSError, ValueError):
        return 'error'
    return 'ok'

class X05System:

    def __init__(self, limit=k.X05_COUNTER_LIMIT):
        self.limit = limit
        self.worker_positions = {}
        self.global_position = 0
        self.issued = []
        self.fail_next = False

    def reserve_worker(self, worker):
        position = self.worker_positions.get(worker, 0)
        if position >= self.limit:
            return None
        self.worker_positions[worker] = position + 1
        return position

    def restart(self, worker):
        return worker

def _x05_packet(system, nonce, payload):
    iv = nonce.to_bytes(k.X05_NONCE_BYTES, 'big')
    system.issued.append(nonce)
    if system.fail_next:
        system.fail_next = False
        return 'encryption-error'
    return iv + AESGCM(bytes(range(32))).encrypt(iv, bytes(payload), k.X05_AAD)

def x05_source(system, worker, payload):
    nonce = system.reserve_worker(worker)
    return 'exhausted' if nonce is None else _x05_packet(system, nonce, payload)

class X06SecretObject:

    def __init__(self, marker='fixture-private'):
        self.marker = marker
        self.representations = 0

    def __repr__(self):
        self.representations += 1
        return self.marker
    __str__ = __repr__

class X06Sink:

    def __init__(self, fail=False):
        self.lines = []
        self.fail = fail

    def write(self, line):
        if self.fail:
            raise OSError('controlled log failure')
        self.lines.append(line)

def _x06_unsafe(record, sink):
    try:
        sink.write(json.dumps(record, sort_keys=True, default=repr))
        return 'logged'
    except (OSError, ValueError, TypeError, RecursionError):
        try:
            sink.write(repr(record))
        except OSError:
            return 'log-error'
        return 'fallback'

def x06_source(record, sink):
    return _x06_unsafe(record, sink)

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

def x07_source(decoder, encoded):
    try:
        envelope = _x07_load(encoded)
        if set(envelope) != {'version', 'data'} or envelope['version'] not in k.X07_VERSIONS:
            return ('invalid', None)

        def source_shape(value, depth=0, count=None):
            count = [0] if count is None else count
            count[0] += 1
            if depth > k.X07_MAX_DEPTH or count[0] > k.X07_MAX_ITEMS:
                return False
            if value is None or isinstance(value, str) or type(value) in (int, bool):
                return True
            if isinstance(value, list):
                return all((source_shape(item, depth + 1, count) for item in value))
            if isinstance(value, dict):
                return all((isinstance(name, str) and source_shape(item, depth + 1, count) for name, item in value.items()))
            return False
        if not source_shape(envelope['data']):
            return ('invalid', None)
        return ('ok', decoder.reconstruct(envelope['data']))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return ('invalid', None)

class X08Sink:

    def __init__(self):
        self.entries = []
        self.work = 0
        self.peak_buffered = 0
        self.cleanup_count = 0

    def publish(self, entries):
        self.entries.extend(((name, bytes(data)) for name, data in entries))

    def cleanup(self):
        self.cleanup_count += 1

def _x08_expand_unbounded(entries, sink):
    prepared = []
    for name, declared, runs in entries:
        data = b''.join((bytes([byte]) * count for count, byte in runs))
        sink.peak_buffered = max(sink.peak_buffered, len(data))
        prepared.append((name, data))
    sink.publish(prepared)
    return 'ok'

def x08_source(entries, sink):
    if len(entries) > k.X08_COUNT_LIMIT:
        return 'limit'
    if any((declared > k.X08_ENTRY_LIMIT for _, declared, _ in entries)) or sum((declared for _, declared, _ in entries)) > k.X08_TOTAL_LIMIT:
        return 'limit'
    return _x08_expand_unbounded(entries, sink)

class X09Store:

    def __init__(self):
        self.effects = []
        self.receipts = {}
        self.before_commit = None

def x09_source(store, identity, meaning, fault=None):
    receipt = ('ack', identity, hashlib.sha256(repr(meaning).encode()).hexdigest()[:12])
    store.effects.append((identity, copy.deepcopy(meaning)))
    if fault == 'after-effect':
        return 'transport-lost'
    return receipt

class X10Sink:

    def __init__(self):
        self.deliveries = []
        self.active_effects = []

    def deliver(self, mode, media_type, filename, payload):
        self.deliveries.append((mode, media_type, filename, bytes(payload)))
        if mode == 'inline' and payload.startswith(b'ACT\x00'):
            self.active_effects.append(payload[4:])

def x10_source(sink, claim, filename, payload):
    if not isinstance(filename, str) or not isinstance(payload, bytes):
        return 'invalid'
    mode = 'inline' if claim in k.X10_PASSIVE_TYPES else 'download'
    sink.deliver(mode, claim if mode == 'inline' else 'application/octet-stream', filename, payload)
    return mode

class X11Workspace:

    def __init__(self, default_readers=('producer', 'consumer')):
        self.default_readers = set(default_readers)
        self.files = {}
        self.observations = []
        self.events = []
        self.next_id = 1

    def create(self, allowed, content):
        identity = self.next_id
        self.next_id += 1
        self.files[identity] = [set(allowed), bytes(content)]
        self.events.append(('create', identity, frozenset(allowed)))
        self._observe(identity)
        return identity

    def permissions(self, identity, allowed):
        self.files[identity][0] = set(allowed)
        self.events.append(('permissions', identity, frozenset(allowed)))
        self._observe(identity)

    def _observe(self, identity):
        allowed, content = self.files[identity]
        for actor in sorted(allowed):
            self.observations.append((actor, content))

    def read(self, identity, actor, fault=None):
        if fault == 'read':
            raise OSError('controlled read failure')
        allowed, content = self.files[identity]
        return content if actor in allowed else None

    def remove(self, identity):
        self.files.pop(identity, None)
        self.events.append(('remove', identity))

def x11_source(workspace, content, fault=None):
    identity = None
    try:
        if fault == 'create':
            raise OSError('controlled create failure')
        identity = workspace.create(workspace.default_readers, content)
        if fault == 'write':
            raise OSError('controlled write failure')
        workspace.permissions(identity, {'producer', 'consumer'})
        if fault == 'handoff':
            raise OSError('controlled handoff failure')
        return ('ok', workspace.read(identity, 'consumer', fault))
    except OSError:
        return ('error', None)
    finally:
        if identity is not None:
            workspace.remove(identity)

@dataclass(frozen=True)
class X12Result:
    exit_code: int
    output: tuple

class X12Child:

    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.effects = []
        self.environments = []

    def run(self, environment):
        environment = dict(environment)
        self.environments.append(environment)
        if environment.get('LOCAL_INIT') == 'append' or environment.get('PYTHONPATH'):
            self.effects.append('authority-change')
        return X12Result(self.exit_code, tuple((environment[name] for name in ('LOCALE', 'DATA', 'TUNING', 'REQUIRED'))))

def x12_source(child, parent, overlay):
    try:
        return child.run({**parent, **overlay})
    except (KeyError, TypeError):
        return X12Result(125, ())
X13_QUANTUM = Decimal('0.01')
X13_MAXIMUM = Decimal(k.X13_MAX_UNITS)

def _x13_quantity(text):
    if not isinstance(text, str):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > X13_MAXIMUM:
        return None
    if value != value.quantize(X13_QUANTUM):
        return None
    return value

def x13_source(account, operation, text):
    value = _x13_quantity(text)
    if value is None:
        return 'invalid'
    if operation == 'debit':
        if int(value) > int(account['remaining']):
            return 'denied'
        account['remaining'] -= value
    elif operation == 'refund':
        if account['remaining'] + value > X13_MAXIMUM:
            return 'invalid'
        account['remaining'] += value
    else:
        return 'invalid'
    return format(account['remaining'], '.2f')

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

def x14_source(context, callbacks):
    references = context.full_references()
    results = []
    for callback in callbacks:
        try:
            results.append(callback.invoke(references))
        except RuntimeError:
            results.append('callback-error')
    return results
import copy
from dataclasses import dataclass
import hashlib
from . import contracts as k

class X16Sessions:

    def __init__(self, now=100, lifetime=20):
        self.rows = {}
        self.now = now
        self.lifetime = lifetime
        self.serial = 0

    def fresh(self):
        self.serial += 1
        return ('server-session', self.serial, object())

    def advance(self, amount):
        self.now += amount

    def active(self, identity):
        row = self.rows.get(identity)
        if row is not None and row.get('expires_at', self.now + 1) <= self.now:
            self.rows.pop(identity, None)
            return None
        return row

def x16_source(store, operation, session, user=None):
    if operation == 'login':
        row = store.rows.setdefault(session, {})
        row['user'] = user
        row['expires_at'] = store.now + store.lifetime
        return session
    if operation == 'logout':
        store.rows.pop(session, None)
        return 'signed-out'
    if operation == 'query':
        row = store.active(session)
        return None if row is None else row.get('user')
    return None

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

def x17_source(store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return store.read()
    if not isinstance(version, str) or not isinstance(left, bytes) or (not isinstance(right, bytes)):
        return 'invalid'
    store.parts.setdefault(version, {})
    store.publish(version)
    if _x17_stopped(stop_after, 'published'):
        return 'paused'
    if _x17_stopped(stop_after, 'before-left'):
        return 'paused'
    store.stage(version, 'left', left)
    if _x17_stopped(stop_after, 'left'):
        return 'paused'
    store.stage(version, 'right', right)
    if _x17_stopped(stop_after, 'right'):
        return 'paused'
    if _x17_stopped(stop_after, 'before-publish'):
        return 'paused'
    if store.atomic:
        store.read()
    return 'complete'

class X20Service:

    def __init__(self):
        self.dispatches = []
        self.writes = []

    def dispatch(self, parsed):
        self.dispatches.append(copy.deepcopy(parsed))
        if parsed['mode'] == 'write':
            self.writes.append('local-write')
        return {'mode': parsed['mode'], 'tags': list(parsed['tags'])}

def x20_source(service, principal, fields):
    if not isinstance(fields, (list, tuple)):
        return 'invalid'
    controls, tags = ([], [])
    for pair in fields:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return 'invalid'
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            return 'invalid'
        if name == 'mode':
            controls.append(value)
        elif name == 'tag':
            tags.append(value)
        else:
            return 'invalid'
    if not controls:
        controls = ['read']
    if any((value not in k.X20_MODES for value in controls)):
        return 'invalid'
    if controls[0] == 'write' and principal != 'writer':
        return 'denied'
    return service.dispatch({'authorization_mode': controls[0], 'mode': controls[-1], 'tags': tags})

@dataclass(frozen=True)
class X21Decision:
    effect: str
    matched: tuple
    reason: str

def _x21_match(selector, resource):
    return selector == '*' or selector == resource

def _x21_apply(effect, resource, effects):
    if effect == 'allow':
        effects.append(resource)

def x21_source(rules, resource, effects):
    for rule_id, effect, selector in rules:
        if _x21_match(selector, resource):
            _x21_apply(effect, resource, effects)
            return X21Decision(effect, (rule_id,), 'first-match')
    return X21Decision('deny', (), 'default-deny')

class X23Kernel:

    def __init__(self, inherited=('readers',), intended=('readers',)):
        self.user = 'launcher'
        self.primary = 'launch'
        self.groups = set(inherited)
        self.intended = set(intended)
        self.failure = None
        self.events = []
        self.executions = []
        self.reads = []

    def set_groups(self, groups):
        self.events.append('groups')
        if self.failure == 'groups' or self.user != 'launcher':
            return False
        self.groups = set(groups)
        return True

    def set_primary(self, group):
        self.events.append('primary')
        if self.failure == 'primary' or self.user != 'launcher':
            return False
        self.primary = group
        return True

    def set_user(self, user):
        self.events.append('user')
        if self.failure == 'user':
            return False
        self.user = user
        return True

    def run(self):
        self.events.append('run')
        self.executions.append((self.user, self.primary, frozenset(self.groups)))
        resources = {'ordinary': ('work', b'job'), 'shared': ('readers', b'shared'), 'analysis': ('analysts', b'analysis'), 'maintenance': ('ops', b'private')}
        for name, (group, data) in resources.items():
            if group == self.primary or group in self.groups:
                self.reads.append((name, data))
        return b'job'

def x23_source(kernel):
    if not kernel.set_primary('work') or not kernel.set_user('worker'):
        return None
    return kernel.run()

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

def x24_source(store, operation, value):
    if operation == 'read':
        return _x24_read(store, value)
    if operation == 'prepare':
        return _x24_prepare(store, value)
    if operation == 'commit':
        group, actor, _revision = value
        store.commit(group, actor)
        return 'committed'
    return 'invalid'

class X26Scratch:

    def __init__(self, previous=b'previous'):
        pattern = previous or b'\xff'
        self.previous = bytes((pattern * k.X26_RECORD_WIDTH)[:k.X26_RECORD_WIDTH])
        self.frames = []
        self.partial_frames = []

    def take(self):
        return bytearray(self.previous)

    def transmit(self, block, fail_after=None):
        value = bytes(block)
        if fail_after is not None:
            if not 0 <= fail_after <= len(value):
                raise ValueError('invalid partial boundary')
            self.partial_frames.append(value[:fail_after])
            return ('error', value[:fail_after])
        self.frames.append(value)
        return ('ok', value)

def x26_source(pool, payload, fail_after=None):
    if not isinstance(payload, bytes) or len(payload) > k.X26_PAYLOAD_LIMIT:
        return ('invalid', None)
    block = pool.take()
    block[0] = len(payload)
    block[1] = 0
    block[2:2 + len(payload)] = payload
    try:
        return pool.transmit(block, fail_after)
    except ValueError:
        return ('invalid', None)

@dataclass(frozen=True)
class X27Decision:
    effect: str
    explanation: str
    pages: int

class X27Pages:
    ERROR = object()

    def __init__(self, pages):
        self.pages = dict(pages)
        self.calls = []
        self.grants = []

    def fetch(self, cursor):
        self.calls.append(cursor)
        return self.pages.get(cursor, self.ERROR)

def x27_source(service, resource):
    page = service.fetch(0)
    if page is service.ERROR or not isinstance(page, tuple) or len(page) != 2:
        return X27Decision('deny', 'service-error', 1)
    restrictions, _continuation = page
    if not isinstance(restrictions, (list, tuple)) or any((not isinstance(item, str) for item in restrictions)):
        return X27Decision('deny', 'malformed-page', 1)
    if resource in restrictions:
        return X27Decision('deny', 'restricted-page-1', 1)
    service.grants.append(resource)
    return X27Decision('allow', 'complete-no-restriction', 1)

class X28Membership:

    def __init__(self, members=(), approximate=False):
        self.members = set(members)
        self.approximate = approximate
        self.grants = []
        self.exact_reads = 0
        self.fail_exact = False

    @staticmethod
    def bucket(item):
        return hashlib.sha256(item.encode('ascii')).digest()[0] % 16

    def preliminary(self, item):
        if not self.approximate:
            return item in self.members
        bits = 0
        for member in self.members:
            bits |= 1 << self.bucket(member)
        return bool(bits & 1 << self.bucket(item))

    def exact(self, item):
        self.exact_reads += 1
        if self.fail_exact:
            raise OSError('controlled authoritative-store failure')
        return item in self.members

def _x28_update(store, operation, item):
    if operation == 'add':
        store.members.add(item)
        return True
    if operation == 'remove':
        store.members.discard(item)
        return True
    return None

def x28_source(store, operation, item):
    update = _x28_update(store, operation, item)
    if update is not None:
        return update
    if operation != 'check':
        return False
    if store.preliminary(item):
        store.grants.append(item)
        return True
    return False
