def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        user_cache = cache.setdefault(user_id, {})
        if document_id not in user_cache:
            user_cache[document_id] = repository.read(user_id, document_id)
        return user_cache[document_id]

    if document_id not in cache:
        cache[document_id] = repository.read(user_id, document_id)
    return cache[document_id]
