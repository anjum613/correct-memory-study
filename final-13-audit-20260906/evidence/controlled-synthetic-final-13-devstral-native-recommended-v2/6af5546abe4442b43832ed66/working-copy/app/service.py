def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        # Use document_id as key for shared cache
        cache_key = document_id
    else:
        # Use user_id + document_id as key for non-shared cache
        cache_key = f"{user_id}:{document_id}"
    
    if cache_key not in cache:
        cache[cache_key] = repository.read(user_id, document_id)
    return cache[cache_key]
