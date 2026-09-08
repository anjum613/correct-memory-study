def load_job(blob: bytes, internal_codec, safe_codec, *, external=False):
    if external:
        raise NotImplementedError("external job imports are not supported")
    return internal_codec.loads(blob)
