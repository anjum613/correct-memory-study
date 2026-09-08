def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        # For shared cache, we assume the cache is a global/shared dictionary
        # that persists across requests
        if document_id not in cache:
            cache[document_id] = repository.read(user_id, document_id)
        return cache[document_id]
    else:
        # For local cache, use same logic but with request-local cache
        if document_id not in cache:
            cache[document_id] = repository.read(user_id, document_id)
        return cache[document_id]
