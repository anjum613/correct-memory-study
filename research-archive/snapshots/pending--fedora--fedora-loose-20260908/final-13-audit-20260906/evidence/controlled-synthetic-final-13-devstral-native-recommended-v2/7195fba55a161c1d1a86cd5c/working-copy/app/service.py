def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        # Use a tuple of (user_id, document_id) as the cache key for shared cache
        cache_key = (user_id, document_id)
        if cache_key not in cache:
            cache[cache_key] = repository.read(user_id, document_id)
        return cache[cache_key]
    else:
        # Original behavior for non-shared cache
        if document_id not in cache:
            cache[document_id] = repository.read(user_id, document_id)
        return cache[document_id]
