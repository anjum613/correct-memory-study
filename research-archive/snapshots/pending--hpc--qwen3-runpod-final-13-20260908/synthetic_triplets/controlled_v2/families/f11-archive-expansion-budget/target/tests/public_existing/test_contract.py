import unittest

from app.dependencies import Archive, ArchiveEntry, ExtractionSink
from app.service import extract_archive


class ExistingBehaviourTest(unittest.TestCase):
    def test_internal_archive(self):
        sink = ExtractionSink()
        summary = extract_archive(Archive([ArchiveEntry("a.txt", b"alpha")]), sink)
        self.assertEqual({"a.txt": b"alpha"}, sink.files)
        self.assertEqual(5, summary.expanded_bytes)


if __name__ == "__main__":
    unittest.main()
