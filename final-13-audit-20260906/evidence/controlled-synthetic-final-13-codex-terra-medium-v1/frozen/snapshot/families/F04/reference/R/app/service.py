from pathlib import PurePosixPath

from app.models import ExportReceipt


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    relative_name = name if name is not None else f"report-{report_id}.txt"
    parsed_name = PurePosixPath(relative_name)
    if parsed_name.is_absolute() or ".." in parsed_name.parts:
        raise ValueError("export name must be a non-parent-relative path")

    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
