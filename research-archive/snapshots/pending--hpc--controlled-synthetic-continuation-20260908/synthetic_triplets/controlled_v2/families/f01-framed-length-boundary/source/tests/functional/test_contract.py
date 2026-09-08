import unittest

from app.dependencies import PayloadSink
from app.service import persist_generated


class SourceFunctionalTest(unittest.TestCase):
    def test_generated_payload_is_persisted(self):
        sink = PayloadSink()
        receipt = persist_generated(b"weekly-report", sink)
        self.assertEqual([b"weekly-report"], sink.items)
        self.assertEqual(13, receipt.stored)


if __name__ == "__main__":
    unittest.main()
