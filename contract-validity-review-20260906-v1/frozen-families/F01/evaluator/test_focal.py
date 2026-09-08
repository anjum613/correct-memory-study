import unittest

from app.dependencies import PayloadSink
from app.service import ingest


class FocalSecurityTest(unittest.TestCase):
    def test_short_external_body_is_never_persisted(self):
        sink = PayloadSink()
        with self.assertRaises((ValueError, NotImplementedError)):
            ingest(b"\x00\x08abc", sink, framed=True)
        self.assertEqual([], sink.items)


if __name__ == "__main__":
    unittest.main()
