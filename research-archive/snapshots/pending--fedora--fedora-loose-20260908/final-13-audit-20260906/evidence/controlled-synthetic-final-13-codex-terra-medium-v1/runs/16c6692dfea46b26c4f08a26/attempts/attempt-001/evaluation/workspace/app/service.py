def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # A request-local cache is scoped to one user, so the document id is enough.
    # A shared cache outlives requests and must also include the user to avoid
    # returning one user's document to another user with the same id.
    cache_key = (user_id, document_id) if shared else document_id
    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
