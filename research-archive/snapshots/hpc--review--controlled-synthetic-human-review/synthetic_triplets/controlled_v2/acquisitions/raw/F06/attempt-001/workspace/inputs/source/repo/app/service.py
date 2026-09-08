def read_from_route(route, document_id: str, broker):
    handle = broker.open(route.workspace)
    return handle.read(document_id)
