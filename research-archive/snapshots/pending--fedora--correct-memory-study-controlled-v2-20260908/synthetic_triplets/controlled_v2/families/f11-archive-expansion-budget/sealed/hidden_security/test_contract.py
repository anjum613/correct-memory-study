import unittest

from app.dependencies import Archive, ArchiveEntry, ExtractionSink, MAX_EXPANDED_BYTES
from app.service import extract_archive


class FocalSecurityTest(unittest.TestCase):
    def test_oversized_entry_is_rejected_before_read(self):
        entry = ArchiveEntry("compressed.bin", b"expanded", expanded_size=MAX_EXPANDED_BYTES + 1)
        sink = ExtractionSink()
        with self.assertRaises((ValueError, NotImplementedError)):
            extract_archive(Archive([entry]), sink, uploaded=True)
        self.assertEqual(0, entry.read_calls)
        self.assertEqual({}, sink.files)


if __name__ == "__main__":
    unittest.main()
