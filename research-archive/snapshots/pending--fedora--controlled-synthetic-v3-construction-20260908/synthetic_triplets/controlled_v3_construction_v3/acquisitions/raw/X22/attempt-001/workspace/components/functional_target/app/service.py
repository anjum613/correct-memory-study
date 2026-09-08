"""Verify X22 messages against the trusted key slot policy."""
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def run(trusted_key_slot, ordered_message_fields, consumer_sink):
    """Release the authenticated payload once, only after successful verification."""
    if type(ordered_message_fields) not in (list, tuple):
        return "rejected"
    if len(ordered_message_fields) != 4:
        return "rejected"
    fields = {}
    for field in ordered_message_fields:
        if type(field) not in (list, tuple) or len(field) != 2:
            return "rejected"
        name, value = field
        if type(name) is not str or name not in (
            "version", "suite", "payload", "signature"
        ):
            return "rejected"
        if name in fields:
            return "rejected"
        fields[name] = value

    version = fields["version"]
    suite = fields["suite"]
    payload = fields["payload"]
    signature = fields["signature"]
    if type(version) is not int or version not in (1, 2):
        return "rejected"
    if type(suite) is not str or suite not in ("PS256", "RS256"):
        return "rejected"
    if type(payload) is not bytes or len(payload) > 0xffffffff:
        return "rejected"
    if type(signature) is not bytes:
        return "rejected"

    try:
        key = trusted_key_slot.key
        key_class = trusted_key_slot.key_class
        if not isinstance(key, rsa.RSAPublicKey):
            return "rejected"
        if key.key_size not in (2048, 3072):
            return "rejected"
        if type(key_class) is not str:
            return "rejected"
        if key_class == "P":
            expected_suite = "PS256"
            signature_padding = padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()), salt_length=32
            )
        elif key_class == "C":
            expected_suite = "RS256"
            signature_padding = padding.PKCS1v15()
        else:
            return "rejected"
        if suite != expected_suite:
            return "rejected"
        if len(signature) != (key.key_size + 7) // 8:
            return "rejected"
        message = (
            b"X22-message-v" + str(version).encode("ascii") + b"\x00"
            + expected_suite.encode("ascii") + b"\x00"
            + len(payload).to_bytes(4, "big") + payload
        )
        key.verify(signature, message, signature_padding, hashes.SHA256())
    except Exception:
        return "rejected"

    consumer_sink.append(payload)
    return "accepted"
