shared_cache = {}
def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        cache = shared_cache
    if document_id not in cache:
        cache[document_id] = repository.read(user_id, document_id)
    return cache[document_id]
