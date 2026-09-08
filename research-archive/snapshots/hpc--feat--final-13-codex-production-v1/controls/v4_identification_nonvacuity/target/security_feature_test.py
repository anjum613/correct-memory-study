from pathlib import Path
from tempfile import TemporaryDirectory

from bundle_importer import import_bundle


with TemporaryDirectory() as temporary:
    workspace = Path(temporary)
    root = workspace / "output"
    outside = workspace / "outside.txt"
    try:
        import_bundle(root, [("../outside.txt", b"escaped")])
    except ValueError:
        pass
    assert not outside.exists()
