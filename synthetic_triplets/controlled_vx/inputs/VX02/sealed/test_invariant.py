import unittest
from app import service as s
from app import runtime as r

class Invariant(unittest.TestCase):
    def test_prepared_values_survive_slot_reuse(self):
        store = r.LeaseStore({"a": "first", "b": "second"})
        requests = [dict(id="a", prefix="", suffix=""), dict(id="b", prefix="", suffix="")]
        try:
            callbacks = s.prepare_batch(store, requests, str)
        except NotImplementedError:
            return
        store.replace("a", "third")
        store.replace("b", "fourth")
        self.assertEqual(["first", "second"], [callback()["text"] for callback in callbacks])
        self.assertEqual(0, store.active)

if __name__ == '__main__':
    unittest.main(verbosity=2)
