"""Serve recorded media classifications in the source context."""


def run(media_sink, claimed_type, filename, payload_bytes):
    if not isinstance(claimed_type, str) or not isinstance(filename, str):
        return "invalid"
    if not isinstance(payload_bytes, bytes):
        return "invalid"

    if claimed_type in ("text/plain", "image/x-local-pixels"):
        media_sink.deliver("inline", claimed_type, filename, payload_bytes)
        return "inline"

    media_sink.deliver("download", "application/octet-stream", filename, payload_bytes)
    return "download"
