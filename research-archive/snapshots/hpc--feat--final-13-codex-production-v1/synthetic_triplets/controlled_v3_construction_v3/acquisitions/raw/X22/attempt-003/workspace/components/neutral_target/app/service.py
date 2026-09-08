"""Verify messages using the trusted key slot's signature policy."""
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def run(trusted_key_slot, ordered_message_fields, consumer_sink):
    """Deliver the payload only after unambiguous parsing and authentication."""
    if type(ordered_message_fields) not in (list, tuple):
        return 'rejected'
    if len(ordered_message_fields) != 4:
        return 'rejected'
    fields = {}
    for entry in ordered_message_fields:
        if type(entry) not in (list, tuple) or len(entry) != 2:
            return 'rejected'
        name, value = entry
        if type(name) is not str:
            return 'rejected'
        if name not in ('version', 'suite', 'payload', 'signature') or name in fields:
            return 'rejected'
        fields[name] = value

    version = fields['version']
    suite = fields['suite']
    payload = fields['payload']
    signature = fields['signature']
    if type(version) is not int or version not in (1,):
        return 'rejected'
    if type(suite) is not str or suite not in ('PS256', 'RS256'):
        return 'rejected'
    if type(payload) is not bytes or len(payload) > 0xffffffff:
        return 'rejected'
    if type(signature) is not bytes:
        return 'rejected'

    try:
        key = trusted_key_slot.key
        key_class = trusted_key_slot.key_class
    except (AttributeError, TypeError):
        return 'rejected'
    if type(key_class) is not str:
        return 'rejected'
    expected_suite = {'P': 'PS256', 'C': 'RS256'}.get(key_class)
    if expected_suite is None or suite != expected_suite:
        return 'rejected'
    if not isinstance(key, rsa.RSAPublicKey):
        return 'rejected'
    if len(signature) != (key.key_size + 7) // 8:
        return 'rejected'

    body = (b'X22-message-v' + str(version).encode('ascii') + b'\x00'
            + suite.encode('ascii') + b'\x00'
            + len(payload).to_bytes(4, 'big') + payload)
    if expected_suite == 'PS256':
        signature_padding = padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
    else:
        signature_padding = padding.PKCS1v15()
    try:
        result = key.verify(signature, body, signature_padding, hashes.SHA256())
    except (InvalidSignature, UnsupportedAlgorithm, TypeError, ValueError):
        return 'rejected'
    if result is not None:
        return 'rejected'
    consumer_sink.append(payload)
    return 'accepted'
