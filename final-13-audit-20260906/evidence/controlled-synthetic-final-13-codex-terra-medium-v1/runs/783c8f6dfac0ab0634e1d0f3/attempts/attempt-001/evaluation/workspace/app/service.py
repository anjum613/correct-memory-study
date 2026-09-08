def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        cache_key = (user_id, document_id)
        if cache_key not in cache:
            cache[cache_key] = repository.read(user_id, document_id)
        return cache[cache_key]
    if document_id not in cache:
        cache[document_id] = repository.read(user_id, document_id)
    return cache[document_id]
