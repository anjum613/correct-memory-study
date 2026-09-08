from pathlib import Path
from tempfile import TemporaryDirectory

from report_writer import make_report_filename, save_report


with TemporaryDirectory() as temporary:
    workspace = Path(temporary)
    root = workspace / "reports"
    generated = make_report_filename("daily")
    assert Path(generated).name == generated
    assert not Path(generated).is_absolute()
    assert ".." not in Path(generated).parts
    saved = save_report(root, "daily", b"safe")
    assert saved.resolve().is_relative_to(root.resolve())
    assert not (workspace / "outside.txt").exists()
