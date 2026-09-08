import unittest
from app import service as s
from app import runtime as r

class Invariant(unittest.TestCase):
    def test_virtual_namespace_is_preserved(self):
        for name in ('../archive/report.txt', '/archive/report.txt', 'team/../../report.txt'):
            store = r.VirtualStore()
            try:
                s.export_batch([dict(id=1, title='A', body='one'), dict(id=2, title='B', body='two', name=name)], store)
            except (ValueError, NotImplementedError):
                pass
            self.assertEqual({}, store.entries)
            self.assertEqual(0, store.commits)

if __name__ == '__main__':
    unittest.main(verbosity=2)
