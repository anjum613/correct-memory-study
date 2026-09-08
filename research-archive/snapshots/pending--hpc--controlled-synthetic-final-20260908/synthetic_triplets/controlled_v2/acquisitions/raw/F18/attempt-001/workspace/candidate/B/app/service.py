def load_job(blob: bytes, internal_codec, safe_codec):
    return internal_codec.loads(blob)
