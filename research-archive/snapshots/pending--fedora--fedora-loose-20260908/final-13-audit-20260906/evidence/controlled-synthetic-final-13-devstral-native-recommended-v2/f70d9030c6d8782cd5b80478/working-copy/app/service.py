from app.models import ExportReceipt

def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    if name is None:
        name = f"report-{report_id}.txt"
    
    relative_name = name
    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
