"""Empty-release baseline; mirrored artifact releases are unavailable."""

import json


def run(release_store, signed_envelope, selection):
    try:
        body, signature = signed_envelope
        if type(body) is not bytes or type(signature) is not bytes:
            return 'invalid'
        metadata = json.loads(body)
        if (type(metadata) is not dict
                or type(metadata.get('artifacts')) is not list):
            return 'invalid'
        if metadata['artifacts'] or selection:
            return 'unsupported'
    except Exception:
        return 'invalid'
    release_store.apply([])
    return 'ok'
