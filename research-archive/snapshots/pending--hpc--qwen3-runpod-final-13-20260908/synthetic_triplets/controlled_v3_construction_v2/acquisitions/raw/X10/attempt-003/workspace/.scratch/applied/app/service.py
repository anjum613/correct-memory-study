"""Serve passive media only when its bytes satisfy the fixed format policy."""


def _classify(payload):
    matches = []
    if payload.startswith(b"TXT\x00"):
        body = payload[4:]
        if body and all(32 <= value <= 126 or value in (9, 10, 13) for value in body):
            matches.append("text/plain")

    if payload.startswith(b"PIX\x00") and len(payload) >= 6:
        width, height = payload[4], payload[5]
        if width and height and len(payload) == 6 + width * height * 3:
            matches.append("image/x-local-pixels")

    # No match or multiple matches cannot authorize inline treatment.
    return matches[0] if len(matches) == 1 else None


def run(media_sink, claimed_type, filename, payload_bytes):
    if not isinstance(claimed_type, str) or not isinstance(filename, str):
        return "invalid"
    if not isinstance(payload_bytes, bytes):
        return "invalid"

    verified_type = _classify(payload_bytes)
    if verified_type is not None and claimed_type == verified_type:
        media_sink.deliver("inline", verified_type, filename, payload_bytes)
        return "inline"

    media_sink.deliver("download", "application/octet-stream", filename, payload_bytes)
    return "download"
