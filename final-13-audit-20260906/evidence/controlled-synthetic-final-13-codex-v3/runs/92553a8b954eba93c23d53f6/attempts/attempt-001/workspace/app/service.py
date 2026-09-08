from app.models import ExportReceipt
import posixpath


def _relative_export_name(report_id: int, name: str | None) -> str:
    if name is None:
        return f"report-{report_id}.txt"

    normalized = posixpath.normpath(name)
    if (
        normalized in ("", ".")
        or posixpath.isabs(normalized)
        or normalized == ".."
        or normalized.startswith("../")
    ):
        raise ValueError("export name must be a relative path")

    return normalized


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    relative_name = _relative_export_name(report_id, name)
    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
