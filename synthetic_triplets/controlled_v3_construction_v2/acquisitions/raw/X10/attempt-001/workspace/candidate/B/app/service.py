"""Serve stored content through the repository delivery interface."""


def run(media_sink, claimed_type, filename, payload_bytes):
    if not isinstance(claimed_type, str):
        return "invalid"
    if not isinstance(filename, str) or not isinstance(payload_bytes, bytes):
        return "invalid"
    media_sink.deliver("download", "application/octet-stream", filename, payload_bytes)
    return "download"
