"""Deliver stored payloads as downloads."""


def run(media_sink, claimed_type, filename, payload_bytes):
    if not isinstance(claimed_type, str) or not isinstance(filename, str):
        return "invalid"
    if not isinstance(payload_bytes, bytes):
        return "invalid"
    media_sink.deliver("download", "application/octet-stream", filename, payload_bytes)
    return "download"
