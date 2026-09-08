def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # A request-local cache can use the document id alone because it belongs to
    # one request/user.  The application-wide cache must include the user in
    # its key so that documents with the same id cannot be shared across users.
    cache_key = (user_id, document_id) if shared else document_id
    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
