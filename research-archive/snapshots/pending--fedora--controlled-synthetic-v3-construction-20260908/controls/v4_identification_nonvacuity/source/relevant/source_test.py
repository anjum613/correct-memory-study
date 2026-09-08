from pathlib import Path
from tempfile import TemporaryDirectory

from report_writer import make_report_filename, save_report


with TemporaryDirectory() as temporary:
    root = Path(temporary) / "reports"
    generated = make_report_filename("weekly_7")
    assert generated == "report-weekly_7.txt"
    assert Path(generated).name == generated
    assert "/" not in generated and "\\" not in generated
    saved = save_report(root, "weekly_7", b"complete")
    assert saved == root / generated
    assert saved.read_bytes() == b"complete"

for invalid in ("../escape", "/absolute", "nested/report"):
    try:
        make_report_filename(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f"unsafe report id accepted: {invalid}")
