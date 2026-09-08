"""Reference-only signed local records. No network, deployed keys or live credentials."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def exact_object(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result
    if type(data) is not bytes:
        raise ValueError("record bytes required")
    value = json.loads(data, object_pairs_hook=pairs)
    if canonical(value) != data:
        raise ValueError("noncanonical record")
    return value


def publisher_key():
    # Published synthetic fixture material, never an operational identity.
    return ed25519.Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def signed_bytes(body, alternate=False):
    key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33))) if alternate else publisher_key()
    return body, key.sign(body)


class ReleaseStore:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.applied = []

    def fetch(self, name):
        return self.objects.get(name)

    def apply(self, values):
        self.applied.extend(values)


def x15_contents(store, envelope, selection):
    try:
        body, signature = envelope
        if type(signature) is not bytes or len(signature) != 64:
            return "invalid"
        statement = exact_object(body)
        if set(statement) != {"version", "release", "artifacts"} or type(statement["version"]) is not int or statement["version"] not in (1, 2):
            return "invalid"
        if type(statement["release"]) is not str or not statement["release"]:
            return "invalid"
        objects = {}
        def collect(nodes, depth=0):
            if depth > 4:
                raise ValueError("artifact depth")
            if type(nodes) is not list:
                raise ValueError("artifact list")
            for node in nodes:
                if len(objects) >= 32:
                    raise ValueError("artifact count")
                if type(node) is not dict or set(node) != {"name", "digest", "children"}:
                    raise ValueError("artifact schema")
                name, digest = node["name"], node["digest"]
                if type(name) is not str or not name or name in objects:
                    raise ValueError("artifact identity")
                if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError("digest representation")
                objects[name] = digest
                collect(node["children"], depth + 1)
        collect(statement["artifacts"])
        if type(selection) not in (list, tuple) or any(type(name) is not str for name in selection):
            return "invalid"
        prepared = []
        for name in dict.fromkeys(selection):
            if name not in objects:
                return "missing"
            content = store.fetch(name)
            if type(content) is not bytes:
                return "missing"
            if hashlib.sha256(content).hexdigest() != objects[name]:
                return "digest"
            prepared.append((name, content))
        store.apply(prepared)
        return "ok"
    except InvalidSignature:
        return "signature"
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        return "invalid"


def x15_source(store, envelope, selection):
    return x15_contents(store, envelope, selection)


def x15_base(store, envelope, selection):
    if selection:
        return "unavailable"
    return x15_repair(store, envelope, selection)


def x15_repair(store, envelope, selection):
    try:
        body, signature = envelope
        publisher_key().public_key().verify(signature, body)
    except InvalidSignature:
        return "signature"
    except (ValueError, TypeError):
        return "invalid"
    return x15_contents(store, envelope, selection)


class Installer:
    def __init__(self, version=2, payload=b"current"):
        self.committed = (version, payload)
        self.pending = None
        self.observations = [self.committed]

    def stage(self, envelope):
        self.pending = envelope
        self.observations.append(self.committed)

    def commit(self, version, payload):
        self.committed = (version, payload)
        self.observations.append(self.committed)
        self.pending = None


def x18_install(store, envelope, interruption):
    if envelope is None:
        envelope = store.pending
    if envelope is None:
        return "offline"
    try:
        body, signature = envelope
        publisher_key().public_key().verify(signature, body)
        record = exact_object(body)
        if set(record) != {"version", "payload_hex"} or type(record["version"]) is not int or not 0 <= record["version"] < 2**63:
            return "invalid"
        payload = bytes.fromhex(record["payload_hex"])
        if payload.hex() != record["payload_hex"]:
            return "invalid"
        version = record["version"]
        if version == store.committed[0]:
            store.pending = None
            return "current" if payload == store.committed[1] else "version-conflict"
        store.stage(envelope)
        if interruption == "staged":
            return "interrupted"
        store.commit(version, payload)
        if interruption == "committed":
            return "interrupted"
        return "installed"
    except InvalidSignature:
        return "signature"
    except (ValueError, TypeError, KeyError, UnicodeError):
        return "invalid"


def x18_source(store, envelope=None, interruption=None):
    return x18_install(store, envelope, interruption)


def x18_base(store, envelope=None, interruption=None):
    if envelope is None:
        return "offline"
    try:
        body, signature = envelope
        publisher_key().public_key().verify(signature, body)
        record = exact_object(body)
        if record["version"] != store.committed[0]:
            return "unavailable"
    except (InvalidSignature, ValueError, TypeError, KeyError, UnicodeError):
        return "invalid"
    return x18_install(store, envelope, interruption)


def x18_repair(store, envelope=None, interruption=None):
    if envelope is None:
        envelope = store.pending
    if envelope is None:
        return "offline"
    try:
        body, signature = envelope
        publisher_key().public_key().verify(signature, body)
        record = exact_object(body)
        if set(record) != {"version", "payload_hex"}:
            return "invalid"
        version = record["version"]
        if type(version) is not int or not 0 <= version < 2**63 or type(record["payload_hex"]) is not str:
            return "invalid"
        payload = bytes.fromhex(record["payload_hex"])
        if payload.hex() != record["payload_hex"]:
            return "invalid"
        if version < store.committed[0]:
            store.pending = None
            return "older"
        if version == store.committed[0] and payload != store.committed[1]:
            store.pending = None
            return "version-conflict"
    except InvalidSignature:
        return "signature"
    except (ValueError, TypeError, KeyError, UnicodeError):
        return "invalid"
    return x18_install(store, envelope, interruption)


@lru_cache(None)
def synthetic_rsa(bits):
    content = json.loads((Path(__file__).with_name("synthetic_rsa_keys.json")).read_text())
    fields = content["keys"][str(bits)]
    return rsa.RSAPrivateNumbers(*(int(fields[k]) for k in ("p", "q", "d", "dmp1", "dmq1", "iqmp")),
                                rsa.RSAPublicNumbers(fields["e"], int(fields["n"]))).private_key()


def suite_padding(suite):
    if suite == "PS256":
        return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
    if suite == "RS256":
        return padding.PKCS1v15()
    raise ValueError("unsupported suite")


def x22_body(version, suite, payload):
    return b"X22-message-v" + str(version).encode("ascii") + b"\0" + suite.encode("ascii") + b"\0" + len(payload).to_bytes(4, "big") + payload


class KeySlot:
    def __init__(self, key, key_class):
        self.key, self.key_class = key, key_class


def x22_source(slot, fields, consumer):
    try:
        if type(fields) not in (list, tuple) or len(fields) != 4:
            return "invalid"
        message = {}
        for pair in fields:
            if type(pair) not in (list, tuple) or len(pair) != 2 or type(pair[0]) is not str or pair[0] in message:
                return "invalid"
            message[pair[0]] = pair[1]
        if set(message) != {"version", "suite", "payload", "signature"}:
            return "invalid"
        version, suite, payload, signature = (message[k] for k in ("version", "suite", "payload", "signature"))
        if type(version) is not int or version not in (1, 2) or type(suite) is not str or suite not in {"PS256", "RS256"}:
            return "invalid"
        if type(payload) is not bytes or len(payload) > 4096 or type(signature) is not bytes:
            return "invalid"
        if not isinstance(slot.key, rsa.RSAPublicKey) or slot.key.key_size not in (2048, 3072) or slot.key.public_numbers().e != 65537 or slot.key_class not in ("P", "C"):
            return "invalid"
        if len(signature) != slot.key.key_size // 8:
            return "invalid"
        slot.key.verify(signature, x22_body(version, suite, payload), suite_padding(suite), hashes.SHA256())
        consumer.append(payload)
        return "accepted"
    except InvalidSignature:
        return "signature"
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError):
        return "invalid"


def x22_base(slot, fields, consumer):
    try:
        message = dict(fields)
        if message.get("payload"):
            return "unavailable"
    except (TypeError, ValueError):
        return "invalid"
    return x22_repair(slot, fields, consumer)


def x22_repair(slot, fields, consumer):
    try:
        if type(fields) not in (tuple, list) or any(type(pair) not in (tuple, list) or len(pair) != 2 for pair in fields):
            return "invalid"
        suites = [value for name, value in fields if name == "suite"]
        if len(suites) != 1 or suites[0] != {"P": "PS256", "C": "RS256"}.get(slot.key_class):
            return "policy"
    except (ValueError, TypeError):
        return "invalid"
    return x22_source(slot, fields, consumer)
