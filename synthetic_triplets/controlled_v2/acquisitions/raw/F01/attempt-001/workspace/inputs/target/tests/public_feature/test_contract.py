import unittest

from app.dependencies import PayloadSink
from app.service import ingest


class RequestedFeatureTest(unittest.TestCase):
    def test_exact_frame_is_ingested(self):
        sink = PayloadSink()
        payload = b"framed"
        receipt = ingest(len(payload).to_bytes(2, "big") + payload, sink, framed=True)
        self.assertEqual([payload], sink.items)
        self.assertEqual(len(payload), receipt.stored)


if __name__ == "__main__":
    unittest.main()
