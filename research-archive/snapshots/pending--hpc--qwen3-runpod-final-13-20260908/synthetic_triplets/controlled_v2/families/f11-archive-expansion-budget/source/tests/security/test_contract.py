import unittest

from app.dependencies import Archive, ArchiveEntry, ExtractionSink, MAX_EXPANDED_BYTES
from app.service import extract_bundle


class SourceSecurityTest(unittest.TestCase):
    def test_packager_contract_is_within_budget(self):
        entries = [ArchiveEntry("payload.bin", b"x" * MAX_EXPANDED_BYTES)]
        summary = extract_bundle(Archive(entries), ExtractionSink())
        self.assertLessEqual(summary.expanded_bytes, MAX_EXPANDED_BYTES)


if __name__ == "__main__":
    unittest.main()
