def get_document(user_id: str, document_id: str, repository, request_cache, shared=False):
    cache_key = (user_id, document_id) if shared else document_id
    if cache_key not in request_cache:
        request_cache[cache_key] = repository.read(user_id, document_id)
    return request_cache[cache_key]
