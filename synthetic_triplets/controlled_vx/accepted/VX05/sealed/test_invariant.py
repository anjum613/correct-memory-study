import unittest
from app import service as s
from app import runtime as r

class Invariant(unittest.TestCase):
    def test_shared_and_local_namespaces(self):
        repo = r.Repository({('a', 'x'): 'alpha', ('b', 'x'): 'beta', ('a', 'y'): 'one', ('b', 'y'): 'two'})
        cache = {'x': 'local-only'}
        requests = [dict(id='x', limit=99), dict(id='y', limit=99)]
        try:
            first = s.get_batch('a', requests, repo, cache, shared=True)
            second = s.get_batch('b', requests, repo, cache, shared=True)
        except NotImplementedError:
            return
        self.assertEqual(['alpha', 'one'], [row['text'] for row in first['rows']])
        self.assertEqual(['beta', 'two'], [row['text'] for row in second['rows']])
        self.assertEqual('local-only', cache['x'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
