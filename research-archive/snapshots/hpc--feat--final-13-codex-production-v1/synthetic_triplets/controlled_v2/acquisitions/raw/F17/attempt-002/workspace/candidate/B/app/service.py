def get_document(user_id: str, document_id: str, repository, request_cache):
    if document_id not in request_cache:
        request_cache[document_id] = repository.read(user_id, document_id)
    return request_cache[document_id]
