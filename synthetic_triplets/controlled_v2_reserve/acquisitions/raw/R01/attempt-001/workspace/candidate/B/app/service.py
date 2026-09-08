from app.models import AuditRecord


def write_login(
    user_id: int, sink, *, display_name: str | None = None
) -> AuditRecord:
    if display_name is not None:
        raise NotImplementedError("display names are not implemented")

    text = f"LOGIN user={user_id}"
    sink.append(text)
    return AuditRecord(text=text)
