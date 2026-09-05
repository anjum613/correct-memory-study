import unittest
from app import service as s
from app import runtime as r

class Existing(unittest.TestCase):
    def test_immediate(self):
        store = r.LeaseStore({"a": "alpha"})
        self.assertEqual("ALPHA", s.render_now(store, "a", str.upper))
        self.assertEqual(0, store.active)

if __name__ == '__main__':
    unittest.main(verbosity=2)
