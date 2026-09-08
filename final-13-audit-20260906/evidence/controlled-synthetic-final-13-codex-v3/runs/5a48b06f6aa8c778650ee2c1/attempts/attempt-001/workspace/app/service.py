def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # Request-local caches are scoped to one user, while a shared cache may
    # contain entries for several users. Keep those namespaces distinct so a
    # document is never served to the wrong user.
    cache_key = (user_id, document_id) if shared else document_id
    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
