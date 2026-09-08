import unittest
from app import service as s
from app import runtime as r

class Feature(unittest.TestCase):
    def test_callbacks_are_lazy_ordered_and_repeatable(self):
        store = r.LeaseStore({"a": "alpha", "b": "beta"})
        requests = [dict(id="a", prefix="[", suffix="]"), dict(id="b", prefix="(", suffix=")"), dict(id="a", prefix="", suffix="!")]
        calls = []
        def formatter(value):
            calls.append(value)
            return value.upper()
        callbacks = s.prepare_batch(store, requests, formatter)
        self.assertEqual([], calls)
        self.assertEqual(0, store.active)
        self.assertEqual(3, len(callbacks))
        self.assertEqual(dict(id="b", text="(BETA)", ordinal=1), callbacks[1]())
        self.assertEqual(dict(id="a", text="[ALPHA]", ordinal=0), callbacks[0]())
        self.assertEqual(dict(id="a", text="alpha".upper()+"!", ordinal=2), callbacks[2]())
        callbacks[0]()
        self.assertEqual(["beta", "alpha", "alpha", "alpha"], calls)
    def test_empty_and_invalid(self):
        store = r.LeaseStore({"a": "alpha"})
        self.assertEqual([], s.prepare_batch(store, [], str))
        for request in (dict(id="missing", prefix="", suffix=""), dict(id="a", prefix=4, suffix="")):
            with self.assertRaises(ValueError):
                s.prepare_batch(store, [dict(id="a", prefix="", suffix=""), request], str)
            self.assertEqual([], store.opens)

if __name__ == '__main__':
    unittest.main(verbosity=2)
