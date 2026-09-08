def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        cache_key = (user_id, document_id)
    else:
        cache_key = document_id

    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
