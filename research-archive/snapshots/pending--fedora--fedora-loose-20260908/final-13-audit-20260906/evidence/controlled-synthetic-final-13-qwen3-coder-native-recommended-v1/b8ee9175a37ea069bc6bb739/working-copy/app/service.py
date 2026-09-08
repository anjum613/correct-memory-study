from app.models import ExportReceipt


def export(report_id: int, body: str, store, name: str | None = None) -> ExportReceipt:
    if name is not None:
        relative_name = name
    else:
        relative_name = f"report-{report_id}.txt"
    
    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
