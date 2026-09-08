def load_queued_job(blob: bytes, codec):
    return codec.loads(blob)
