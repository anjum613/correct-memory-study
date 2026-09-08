def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if not shared:
        # Local cache behavior - the original implementation
        if document_id not in cache:
            cache[document_id] = repository.read(user_id, document_id)
        return cache[document_id]
    else:
        # Shared cache behavior - use the same cache for all requests
        if document_id not in cache:
            cache[document_id] = repository.read(user_id, document_id)
        return cache[document_id]
