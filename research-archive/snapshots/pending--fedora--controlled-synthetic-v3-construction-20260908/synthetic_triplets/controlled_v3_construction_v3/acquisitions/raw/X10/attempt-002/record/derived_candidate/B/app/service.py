"""Download-only baseline for publisher-supplied media."""


def run(media_sink, claimed_type, filename, payload_bytes):
    if not (
        isinstance(claimed_type, str)
        and isinstance(filename, str)
        and isinstance(payload_bytes, bytes)
    ):
        return 'invalid'
    media_sink.deliver(
        'download', 'application/octet-stream', filename, payload_bytes
    )
    return 'download'
