def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    # Create a cache key based on whether we're using shared cache or not
    if shared:
        key = (user_id, document_id)
    else:
        key = document_id
        
    # Check if the document is in the cache
    if key not in cache:
        # Cache miss - read from repository and store in cache
        cache[key] = repository.read(user_id, document_id)
    
    # Return the cached document
    return cache[key]
