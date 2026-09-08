def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # Both shared and non-shared modes use the same cache dictionary
    # The difference is in how the cache is managed externally
    if document_id not in cache:
        cache[document_id] = repository.read(user_id, document_id)
    return cache[document_id]
