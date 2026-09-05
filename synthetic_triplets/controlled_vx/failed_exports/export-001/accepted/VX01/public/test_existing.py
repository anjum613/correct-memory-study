import unittest
from app import service as s
from app import runtime as r

class Existing(unittest.TestCase):
    def test_raw(self):
        for body in (b"", b"abc", bytes(range(32))):
            sink = r.MemorySink()
            self.assertEqual(len(body), s.ingest_raw(body, sink))
            self.assertEqual(body, sink.batches[0][0]["body"])

if __name__ == '__main__':
    unittest.main(verbosity=2)
