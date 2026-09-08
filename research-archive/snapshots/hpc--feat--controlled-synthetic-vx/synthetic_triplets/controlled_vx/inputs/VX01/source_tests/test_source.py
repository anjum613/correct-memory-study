import unittest
from app import service as s
from app import runtime as r

class Source(unittest.TestCase):
    def test_generated_batches(self):
        for reverse in (False, True):
            rows = [{"id": "a", "body": b"ab"}, {"id": "b", "body": b"c"}]
            sink = r.MemorySink()
            got = s.ingest_generated(rows, sink, reverse=reverse)
            self.assertEqual(["b", "a"] if reverse else ["a", "b"], got["ids"])
            self.assertEqual(3, got["total_bytes"])
            self.assertEqual(1, len(sink.batches))
    def test_empty(self):
        self.assertEqual(0, s.ingest_generated([], r.MemorySink())["count"])

if __name__ == '__main__':
    unittest.main(verbosity=2)
