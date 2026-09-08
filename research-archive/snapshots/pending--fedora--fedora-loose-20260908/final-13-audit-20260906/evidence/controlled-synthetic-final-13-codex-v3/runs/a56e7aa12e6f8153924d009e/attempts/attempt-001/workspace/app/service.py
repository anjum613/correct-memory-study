import posixpath

from app.models import ExportReceipt


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    relative_name = f"report-{report_id}.txt" if name is None else name

    if not relative_name or posixpath.isabs(relative_name):
        raise ValueError("export name must be a non-empty relative path")

    normalized_name = posixpath.normpath(relative_name)
    if normalized_name == ".." or normalized_name.startswith("../"):
        raise ValueError("export name must remain beneath the export root")

    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
