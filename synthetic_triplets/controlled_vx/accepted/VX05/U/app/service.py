def get_one(user, key, repository, cache):
    if key not in cache:
        cache[key] = repository.read(user, key)
    return cache[key]

def get_batch(user, requests, repository, cache, *, shared=False):
    prepared = []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError('invalid projection request')
        key, limit = request.get('id'), request.get('limit')
        if not isinstance(key, str) or not key or type(limit) is not int or limit < 0:
            raise ValueError('invalid projection request')
        prepared.append((key, limit))

    rows = []
    characters = 0
    reads = 0
    for key, limit in prepared:
        cache_key = ('shared', key) if shared else key
        if cache_key not in cache:
            cache[cache_key] = repository.read(user, key)
            reads += 1
        body = cache[cache_key]
        text = body[:limit]
        rows.append({'id': key, 'text': text, 'full_length': len(body)})
        characters += len(text)
    return {'rows': rows, 'characters': characters, 'repository_reads': reads}
