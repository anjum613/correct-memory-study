"""Deliver passive media only after validating its complete byte format."""


def _classify(payload):
    if payload.startswith(b"TXT\x00"):
        body = payload[4:]
        if body and all(byte in (9, 10, 13) or 32 <= byte <= 126 for byte in body):
            return "text/plain"
        return None

    if payload.startswith(b"PIX\x00"):
        if len(payload) >= 6:
            width, height = payload[4], payload[5]
            if width and height and len(payload) == 6 + width * height * 3:
                return "image/x-local-pixels"
        return None

    return None


def run(media_sink, claimed_type, filename, payload_bytes):
    if not (
        isinstance(claimed_type, str)
        and isinstance(filename, str)
        and isinstance(payload_bytes, bytes)
    ):
        return "invalid"

    verified_type = _classify(payload_bytes)
    if verified_type is not None and claimed_type == verified_type:
        media_sink.deliver("inline", verified_type, filename, payload_bytes)
        return "inline"

    media_sink.deliver(
        "download", "application/octet-stream", filename, payload_bytes
    )
    return "download"
