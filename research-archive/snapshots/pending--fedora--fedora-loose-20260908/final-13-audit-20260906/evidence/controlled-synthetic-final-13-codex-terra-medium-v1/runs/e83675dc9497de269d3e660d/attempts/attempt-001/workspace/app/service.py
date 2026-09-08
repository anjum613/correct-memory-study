import posixpath

from app.models import ExportReceipt


def export(
    report_id: int,
    body: str,
    store,
    name: str | None = None,
) -> ExportReceipt:
    if name is None:
        relative_name = f"report-{report_id}.txt"
    else:
        if not isinstance(name, str):
            raise TypeError("name must be a string")

        # The store joins names beneath its export root, so reject names that
        # could cause that join to address a location outside it.
        relative_name = posixpath.normpath(name)
        if (
            not name
            or posixpath.isabs(name)
            or relative_name in (".", "..")
            or relative_name.startswith("../")
        ):
            raise ValueError("name must be a relative export name")

    store.write(relative_name, body)
    return ExportReceipt(path=relative_name)
