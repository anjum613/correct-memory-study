def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # Request-local caches are scoped to one user, so the document id is
    # sufficient.  A shared cache outlives a request and must include the
    # user in its key to avoid returning another user's document.
    cache_key = (user_id, document_id) if shared else document_id
    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
