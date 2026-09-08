from app.models import ExportReceipt
import posixpath


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    if name is not None:
        normalized_name = posixpath.normpath(name)
        if (
            not name
            or "\x00" in name
            or posixpath.isabs(name)
            or normalized_name == ".."
            or normalized_name.startswith("../")
        ):
            raise ValueError("export name must be a relative path")
        relative_name = name
    else:
        relative_name = f"report-{report_id}.txt"

    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
