def get_one(user, key, repository, cache):
    if key not in cache:
        cache[key] = repository.read(user, key)
    return cache[key]

def get_batch(user, requests, repository, cache, *, shared=False):
    raise NotImplementedError('batch document projections')
