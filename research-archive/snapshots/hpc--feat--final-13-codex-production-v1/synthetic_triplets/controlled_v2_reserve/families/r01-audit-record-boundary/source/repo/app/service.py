from app.models import AuditRecord


def write_login(user_id: int, sink) -> AuditRecord:
    text = f"LOGIN user={user_id}"
    sink.append(text)
    return AuditRecord(text=text)
