def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # A request-local cache belongs to one user, but a shared cache can be
    # observed by many users.  Scope shared entries by principal to avoid a
    # document ID collision returning another user's document.
    cache_key = (user_id, document_id) if shared else document_id

    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
