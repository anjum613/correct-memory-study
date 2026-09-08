def receive_internal(body: str, handler):
    return handler.handle(body)
