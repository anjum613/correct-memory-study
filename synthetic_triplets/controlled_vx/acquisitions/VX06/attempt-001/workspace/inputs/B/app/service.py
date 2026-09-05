def fetch_one(path, session, transport):
    origin = (session.origin[0].lower(), session.origin[1].lower(), session.origin[2])
    return transport.fetch(origin, path, marker=session.marker)

def fetch_manifest(entries, session, transport):
    raise NotImplementedError('resource manifests')
