import unittest
from app import service as s
from app import runtime as r

class Feature(unittest.TestCase):
    def test_order_and_summary(self):
        for reverse in (False, True):
            rows = [{"id": "a", "declared_size": 2, "body": b"ab"},
                    {"id": "b", "declared_size": 0, "body": b""},
                    {"id": "c", "declared_size": 1, "body": b"z"}]
            before = [dict(row) for row in rows]
            sink = r.MemorySink()
            got = s.ingest_batch(rows, sink, reverse=reverse)
            ids, sizes, offsets = (["c", "b", "a"], [1, 0, 2], [0, 1, 1]) if reverse else (["a", "b", "c"], [2, 0, 1], [0, 2, 2])
            self.assertEqual(dict(ids=ids, sizes=sizes, offsets=offsets, total_bytes=3, count=3), got)
            self.assertEqual(ids, [row["id"] for row in sink.batches[0]])
            self.assertEqual(offsets, [row["offset"] for row in sink.batches[0]])
            self.assertEqual(before, rows)
            self.assertEqual(1, len(sink.batches))
    def test_empty(self):
        sink = r.MemorySink()
        self.assertEqual(dict(ids=[], sizes=[], offsets=[], total_bytes=0, count=0), s.ingest_batch([], sink))
        self.assertEqual([[]], sink.batches)
    def test_structural_rejection_is_atomic(self):
        good = {"id": "a", "declared_size": 1, "body": b"a"}
        for bad in ({"id": "", "declared_size": 1, "body": b"x"}, dict(good),
                    {"id": "b", "declared_size": -1, "body": b"x"},
                    {"id": "b", "declared_size": 1, "body": "x"}):
            sink = r.MemorySink()
            with self.assertRaises(ValueError):
                s.ingest_batch([good, bad], sink)
            self.assertEqual([], sink.batches)

if __name__ == '__main__':
    unittest.main(verbosity=2)
