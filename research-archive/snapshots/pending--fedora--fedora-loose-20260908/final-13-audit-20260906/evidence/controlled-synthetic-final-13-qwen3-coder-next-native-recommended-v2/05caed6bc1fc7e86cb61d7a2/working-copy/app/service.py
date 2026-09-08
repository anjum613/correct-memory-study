from app.models import ExportReceipt


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    if name is None:
        name = f"report-{report_id}.txt"
    
    store.write(name, body)
    return ExportReceipt(path=name)
