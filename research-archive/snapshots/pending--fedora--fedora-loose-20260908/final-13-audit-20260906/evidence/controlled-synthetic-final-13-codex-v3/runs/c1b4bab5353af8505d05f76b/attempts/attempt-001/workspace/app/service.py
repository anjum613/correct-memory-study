def get_document(user_id: str, document_id: str, repository, cache, shared=False):
    if shared:
        if user_id not in cache:
            cache[user_id] = {}
        if document_id not in cache[user_id]:
            cache[user_id][document_id] = repository.read(user_id, document_id)
        return cache[user_id][document_id]

    if document_id not in cache:
        cache[document_id] = repository.read(user_id, document_id)
    return cache[document_id]
