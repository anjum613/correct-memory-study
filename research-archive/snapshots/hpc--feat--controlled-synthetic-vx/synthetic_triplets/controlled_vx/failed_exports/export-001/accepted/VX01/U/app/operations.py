"""Implementation helpers for this application."""


def validate_frames(frames):
    """Materialize a batch and validate its fields before staging rows."""
    try:
        frames = list(frames)
    except TypeError as exc:
        raise ValueError("frames must be iterable") from exc

    seen = set()
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("frame must be a dict")
        frame_id = frame.get("id")
        if not isinstance(frame_id, str) or not frame_id or frame_id in seen:
            raise ValueError("invalid or duplicate id")
        declared_size = frame.get("declared_size")
        if (
            not isinstance(declared_size, int)
            or isinstance(declared_size, bool)
            or declared_size < 0
        ):
            raise ValueError("declared_size must be a nonnegative integer")
        if not isinstance(frame.get("body"), bytes):
            raise ValueError("body must be bytes")
        seen.add(frame_id)
    return frames
