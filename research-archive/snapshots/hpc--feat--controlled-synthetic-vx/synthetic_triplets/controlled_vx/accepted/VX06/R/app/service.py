from app.operations import normalize_origin


def fetch_one(path, session, transport):
    origin = (session.origin[0].lower(), session.origin[1].lower(), session.origin[2])
    return transport.fetch(origin, path, marker=session.marker)


def fetch_manifest(entries, session, transport):
    session_origin = normalize_origin(session.origin)
    prepared = []
    seen_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('invalid manifest entry')
        identifier, path = entry.get('id'), entry.get('path')
        if not isinstance(identifier, str) or not identifier or identifier in seen_ids:
            raise ValueError('invalid or duplicate id')
        if not isinstance(path, str) or not path:
            raise ValueError('invalid resource path')
        origin = normalize_origin(entry.get('origin', session_origin))
        seen_ids.add(identifier)
        prepared.append((identifier, origin, path))

    cache = {}
    rows = []
    characters = 0
    for identifier, origin, path in prepared:
        key = (origin, path)
        if key not in cache:
            cache[key] = transport.fetch(
                origin, path,
                marker=session.marker if origin == session_origin else None,
            )
        body = cache[key]
        rows.append({'id': identifier, 'origin': origin, 'path': path, 'body': body})
        characters += len(body)
    return {'rows': rows, 'fetches': len(cache), 'characters': characters}
