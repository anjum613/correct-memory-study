def receive_event(body: str, handler, verifier, *, external=False, signature=None):
    if external:
        raise NotImplementedError("external event delivery is not implemented")
    return handler.handle(body)
