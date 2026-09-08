def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        # A long-lived cache is shared by multiple principals, so its entries
        # must include the user identity as well as the document identifier.
        cache_key = (user_id, document_id)
    else:
        # Request-local caches retain their existing document-id-only layout.
        cache_key = document_id

    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
