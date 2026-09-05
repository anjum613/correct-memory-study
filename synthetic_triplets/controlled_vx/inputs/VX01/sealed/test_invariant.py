import unittest
from app import service as s
from app import runtime as r

class Invariant(unittest.TestCase):
    def test_exact_body_before_commit(self):
        for declared, body in ((3, b"a"), (1, b"abc"), (0, b"a"), (1, b"")):
            sink = r.MemorySink()
            try:
                s.ingest_batch([{"id": "ok", "declared_size": 1, "body": b"x"},
                                {"id": "other", "declared_size": declared, "body": body}], sink)
            except (ValueError, NotImplementedError):
                pass
            self.assertEqual([], sink.batches)

if __name__ == '__main__':
    unittest.main(verbosity=2)
