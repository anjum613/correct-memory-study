from app.dependencies import generated_metadata


def apply_metadata(response, request_id: str, client_metadata=None):
    response.headers.update(generated_metadata(request_id))
    return response
