def fetch_local_manifest(entries, session, transport):
    origin = (session.origin[0].lower(), session.origin[1].lower(), session.origin[2])
    prepared = []
    seen_ids = set()
    for entry in entries:
        identifier, path = entry.get('id'), entry.get('path')
        if not isinstance(identifier, str) or not identifier or identifier in seen_ids:
            raise ValueError('invalid or duplicate id')
        if not isinstance(path, str) or not path:
            raise ValueError('invalid resource path')
        seen_ids.add(identifier)
        prepared.append((identifier, path))
    cache = {}
    rows = []
    characters = 0
    for identifier, path in prepared:
        key = (origin, path)
        if key not in cache:
            cache[key] = transport.fetch(origin, path, marker=session.marker)
        body = cache[key]
        rows.append({'id': identifier, 'origin': origin, 'path': path, 'body': body})
        characters += len(body)
    return {'rows': rows, 'fetches': len(cache), 'characters': characters}
