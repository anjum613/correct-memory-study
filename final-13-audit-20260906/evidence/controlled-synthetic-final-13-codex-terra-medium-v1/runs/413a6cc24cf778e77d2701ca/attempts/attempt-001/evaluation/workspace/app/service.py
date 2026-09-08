from app.models import ExportReceipt
import posixpath


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    if name is None:
        relative_name = f"report-{report_id}.txt"
    else:
        normalized_name = posixpath.normpath(name)
        if (
            not name
            or posixpath.isabs(name)
            or normalized_name in (".", "..")
            or normalized_name.startswith("../")
        ):
            raise ValueError("export name must be a relative path within the export root")

        relative_name = name

    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
