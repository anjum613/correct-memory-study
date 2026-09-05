def get_local_batch(user, requests, repository, cache):
    prepared = []
    for request in requests:
        key, limit = request.get('id'), request.get('limit')
        if not isinstance(key, str) or not key or type(limit) is not int or limit < 0:
            raise ValueError('invalid projection request')
        prepared.append((key, limit))
    rows = []
    characters = 0
    reads = 0
    for key, limit in prepared:
        if key not in cache:
            cache[key] = repository.read(user, key)
            reads += 1
        body = cache[key]
        text = body[:limit]
        rows.append({'id': key, 'text': text, 'full_length': len(body)})
        characters += len(text)
    return {'rows': rows, 'characters': characters, 'repository_reads': reads}
