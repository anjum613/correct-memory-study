from app.models import ExportReceipt


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:

    relative_name = name if name is not None else f"report-{report_id}.txt"
    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
