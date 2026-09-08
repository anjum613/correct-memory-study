import unittest

from app.dependencies import Archive, ArchiveEntry, ExtractionSink
from app.service import extract_archive


class RequestedFeatureTest(unittest.TestCase):
    def test_small_uploaded_archive(self):
        sink = ExtractionSink()
        archive = Archive([ArchiveEntry("upload.txt", b"small")])
        summary = extract_archive(archive, sink, uploaded=True)
        self.assertEqual({"upload.txt": b"small"}, sink.files)
        self.assertEqual((1, 5), (summary.files, summary.expanded_bytes))


if __name__ == "__main__":
    unittest.main()
