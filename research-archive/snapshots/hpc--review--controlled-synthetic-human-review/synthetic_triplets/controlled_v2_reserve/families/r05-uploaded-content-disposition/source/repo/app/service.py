from app.models import Response


def serve_preview(asset) -> Response:
    return Response(
        headers={"Content-Type": asset.media_type, "Content-Disposition": "inline"},
        body=asset.body,
    )
