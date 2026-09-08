from pathlib import Path
from tempfile import TemporaryDirectory

from report_writer import save_report


with TemporaryDirectory() as temporary:
    workspace = Path(temporary)
    root = workspace / "reports"
    outside = workspace / "outside.txt"
    save_report(root, "../outside.txt", b"escaped")
    assert not outside.exists()
