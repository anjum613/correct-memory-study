def read_document(session, document_id: str, broker, workspace=None):
    if workspace is not None:
        raise NotImplementedError("workspace selection is not implemented")

    handle = broker.open(session.default_workspace)
    return handle.read(document_id)
