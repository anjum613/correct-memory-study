from pathlib import Path
from tempfile import TemporaryDirectory

from report_writer import save_report


with TemporaryDirectory() as temporary:
    root = Path(temporary) / "reports"
    saved = save_report(root, "weekly_7", b"complete")
    assert saved == root / "weekly_7"
    assert saved.read_bytes() == b"complete"
