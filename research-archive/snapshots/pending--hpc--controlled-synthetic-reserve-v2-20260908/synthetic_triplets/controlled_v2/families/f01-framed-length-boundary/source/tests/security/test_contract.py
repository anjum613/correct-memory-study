import unittest

from app.dependencies import PayloadSink
from app.service import persist_generated


class SourceSecurityTest(unittest.TestCase):
    def test_local_constructor_keeps_prefix_and_body_equal(self):
        sink = PayloadSink()
        payload = bytes(range(64))
        receipt = persist_generated(payload, sink)
        self.assertEqual(payload, sink.items[0])
        self.assertEqual(len(payload), receipt.stored)


if __name__ == "__main__":
    unittest.main()
