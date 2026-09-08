"""Complete fixed-width responses with initialized public padding."""


def run(scratch_pool, payload_bytes, fail_after=None):
    if not isinstance(payload_bytes, bytes) or len(payload_bytes) > 14:
        return ("invalid", None)

    block = scratch_pool.take()
    # Initialize reserved and unused payload bytes before any transmission.
    block[:] = bytes(16)
    block[0] = len(payload_bytes)
    block[2:2 + len(payload_bytes)] = payload_bytes
    return scratch_pool.transmit(block, fail_after=fail_after)
