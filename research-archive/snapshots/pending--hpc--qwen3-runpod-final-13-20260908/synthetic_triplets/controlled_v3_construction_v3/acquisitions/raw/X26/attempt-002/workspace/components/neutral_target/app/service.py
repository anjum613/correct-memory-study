"""Fixed-width response for the existing full-payload interface."""


def run(scratch_pool, payload_bytes, fail_after=None):
    if not isinstance(payload_bytes, bytes) or len(payload_bytes) != 14:
        return ("invalid", None)

    block = scratch_pool.take()
    block[0] = len(payload_bytes)
    block[1] = 0
    block[2:16] = payload_bytes
    return scratch_pool.transmit(block, fail_after=fail_after)
