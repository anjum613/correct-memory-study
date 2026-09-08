def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        # For shared cache, we use the same logic but expect the cache to be application-wide
        if document_id not in cache:
            cache[document_id] = repository.read(user_id, document_id)
        return cache[document_id]
    if document_id not in cache:
        cache[document_id] = repository.read(user_id, document_id)
    return cache[document_id]
