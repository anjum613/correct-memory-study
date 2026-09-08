"""Authenticate messages under the trusted RSA key-slot policy."""
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def run(trusted_key_slot, ordered_message_fields, consumer_sink):
    try:
        # Parse once, without allowing duplicate fields to override one another.
        fields = {}
        for entry in ordered_message_fields:
            if type(entry) not in (tuple, list) or len(entry) != 2:
                return 'rejected'
            name, value = entry
            if type(name) is not str or name not in (
                'version', 'suite', 'payload', 'signature'
            ) or name in fields:
                return 'rejected'
            fields[name] = value
        if len(fields) != 4:
            return 'rejected'
        version = fields['version']
        suite = fields['suite']
        payload = fields['payload']
        signature = fields['signature']
        if type(version) is not int or version not in (1, 2):
            return 'rejected'
        if type(suite) is not str or suite not in ('PS256', 'RS256'):
            return 'rejected'
        if type(payload) is not bytes or len(payload) > 0xffffffff:
            return 'rejected'
        if type(signature) is not bytes:
            return 'rejected'

        key = trusted_key_slot.key
        key_class = trusted_key_slot.key_class
        if not isinstance(key, rsa.RSAPublicKey):
            return 'rejected'
        if type(key_class) is not str or key_class not in ('P', 'C'):
            return 'rejected'
        # P is PSS-only; C additionally permits the RSA compatibility suite.
        if key_class == 'P' and suite != 'PS256':
            return 'rejected'
        if len(signature) != (key.key_size + 7) // 8:
            return 'rejected'
        if suite == 'PS256':
            scheme = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
        else:
            scheme = padding.PKCS1v15()
        body = (b'X22-message-v' + str(version).encode('ascii') + b'\x00'
                + suite.encode('ascii') + b'\x00'
                + len(payload).to_bytes(4, 'big') + payload)
        key.verify(signature, body, scheme, hashes.SHA256())
    except Exception:
        return 'rejected'
    consumer_sink.append(payload)
    return 'accepted'
