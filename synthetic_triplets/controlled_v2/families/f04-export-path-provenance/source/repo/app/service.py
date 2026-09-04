from app.models import ExportReceipt


def export_generated(report_id: int, body: str, store) -> ExportReceipt:
    name = f"report-{report_id}.txt"
    store.write(name, body)
    return ExportReceipt(path=name)
