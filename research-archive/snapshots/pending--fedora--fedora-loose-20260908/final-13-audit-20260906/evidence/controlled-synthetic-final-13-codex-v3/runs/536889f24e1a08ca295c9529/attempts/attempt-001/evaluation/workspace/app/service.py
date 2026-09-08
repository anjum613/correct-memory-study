def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # Request-local caches are isolated to one user, so retain the existing
    # document-id key.  A shared cache may contain entries for multiple users;
    # include the user in its key to prevent cross-user cache hits.
    cache_key = (user_id, document_id) if shared else document_id
    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
