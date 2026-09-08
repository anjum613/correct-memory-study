from pathlib import Path
from tempfile import TemporaryDirectory

from bundle_importer import import_bundle


with TemporaryDirectory() as temporary:
    root = Path(temporary) / "output"
    written = import_bundle(root, [("docs/readme.txt", b"hello")])
    expected = root / "docs" / "readme.txt"
    assert written == [expected]
    assert expected.read_bytes() == b"hello"
