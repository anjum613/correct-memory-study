import posixpath

from app.models import ExportReceipt


def _export_name(report_id: int, name: str | None) -> str:
    if name is None:
        return f"report-{report_id}.txt"

    relative_name = posixpath.normpath(name)
    if (
        not name
        or posixpath.isabs(name)
        or relative_name == "."
        or relative_name == ".."
        or relative_name.startswith("../")
    ):
        raise ValueError("export name must be a relative path")

    return relative_name


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    relative_name = _export_name(report_id, name)
    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
