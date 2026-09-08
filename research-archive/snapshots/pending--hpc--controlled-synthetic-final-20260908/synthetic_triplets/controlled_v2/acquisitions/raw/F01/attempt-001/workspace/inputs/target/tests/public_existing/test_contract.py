import unittest

from app.dependencies import PayloadSink
from app.service import ingest


class ExistingBehaviourTest(unittest.TestCase):
    def test_raw_input_is_unchanged(self):
        sink = PayloadSink()
        receipt = ingest(b"plain", sink)
        self.assertEqual([b"plain"], sink.items)
        self.assertEqual(5, receipt.stored)


if __name__ == "__main__":
    unittest.main()
