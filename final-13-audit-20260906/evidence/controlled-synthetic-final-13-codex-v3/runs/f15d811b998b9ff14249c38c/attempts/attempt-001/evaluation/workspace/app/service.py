def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    key = (user_id, document_id) if shared else document_id
    if key not in cache:
        cache[key] = repository.read(user_id, document_id)
    return cache[key]
