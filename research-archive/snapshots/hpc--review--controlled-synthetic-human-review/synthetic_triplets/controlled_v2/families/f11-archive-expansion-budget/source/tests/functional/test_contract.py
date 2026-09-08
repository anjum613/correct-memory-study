import unittest

from app.dependencies import Archive, ArchiveEntry, ExtractionSink
from app.service import extract_bundle


class SourceFunctionalTest(unittest.TestCase):
    def test_internal_bundle_extracts(self):
        archive = Archive([ArchiveEntry("a.txt", b"alpha"), ArchiveEntry("b.txt", b"beta")])
        sink = ExtractionSink()
        summary = extract_bundle(archive, sink)
        self.assertEqual({"a.txt": b"alpha", "b.txt": b"beta"}, sink.files)
        self.assertEqual((2, 9), (summary.files, summary.expanded_bytes))


if __name__ == "__main__":
    unittest.main()
