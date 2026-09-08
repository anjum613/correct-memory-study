def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # A request-local cache only needs the document ID: each request belongs to
    # one user.  A shared, application-wide cache must include the user ID to
    # avoid returning one user's document to another user with the same ID.
    cache_key = (user_id, document_id) if shared else document_id

    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
