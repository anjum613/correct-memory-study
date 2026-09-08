from app.dependencies import generated_metadata


def apply_generated(response, request_id: str):
    response.headers.update(generated_metadata(request_id))
    return response
