def generated_metadata(request_id):
    return {"X-Request-ID": request_id, "Cache-Control": "private"}
