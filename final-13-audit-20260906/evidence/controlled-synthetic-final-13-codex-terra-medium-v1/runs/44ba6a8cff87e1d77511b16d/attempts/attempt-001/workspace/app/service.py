from app.models import ExportReceipt


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    relative_name = f"report-{report_id}.txt" if name is None else name
    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
