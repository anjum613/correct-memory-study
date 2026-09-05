import unittest
from app import service as s
from app import runtime as r

class Source(unittest.TestCase):
    def test_immediate_batch(self):
        store = r.LeaseStore({"a": "alpha", "b": "beta"})
        requests = [dict(id="a", prefix="[", suffix="]"), dict(id="b", prefix="(", suffix=")")]
        result = s.render_batch_now(store, requests, str.upper)
        store.replace("a", "updated")
        self.assertEqual([dict(id="a", text="[ALPHA]", ordinal=0), dict(id="b", text="(BETA)", ordinal=1)], result)
        self.assertEqual(0, store.active)

if __name__ == '__main__':
    unittest.main(verbosity=2)
