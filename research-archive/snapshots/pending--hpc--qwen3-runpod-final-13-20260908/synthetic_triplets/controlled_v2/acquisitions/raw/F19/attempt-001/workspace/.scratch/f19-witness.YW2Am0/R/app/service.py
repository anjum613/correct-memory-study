from app.dependencies import generated_metadata


def apply_metadata(response, request_id: str, client_metadata=None):
    response.headers.update(generated_metadata(request_id))
    if client_metadata is not None:
        display_metadata = {
            key: value
            for key, value in client_metadata.items()
            if key in {"X-Label", "X-Color"}
        }
        response.headers.update(display_metadata)
    return response
