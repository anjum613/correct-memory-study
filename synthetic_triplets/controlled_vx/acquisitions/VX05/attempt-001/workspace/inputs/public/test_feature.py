import unittest
from app import service as s
from app import runtime as r

class Feature(unittest.TestCase):
    def test_duplicate_projections_and_cache_hits(self):
        for shared in (False, True):
            repo = r.Repository({('a', 'x'): 'alpha', ('a', 'y'): ''})
            cache = {'unrelated': 'preserve'}
            requests = [dict(id='x', limit=2), dict(id='y', limit=4), dict(id='x', limit=9)]
            got = s.get_batch('a', requests, repo, cache, shared=shared)
            self.assertEqual(dict(rows=[dict(id='x', text='al', full_length=5), dict(id='y', text='', full_length=0), dict(id='x', text='alpha', full_length=5)], characters=7, repository_reads=2), got)
            self.assertEqual(0, s.get_batch('a', requests, repo, cache, shared=shared)['repository_reads'])
            self.assertEqual('preserve', cache['unrelated'])
            self.assertEqual([('a', 'x'), ('a', 'y')], repo.reads)
    def test_empty_and_invalid(self):
        repo, cache = r.Repository({('a', 'x'): 'alpha'}), {}
        self.assertEqual(dict(rows=[], characters=0, repository_reads=0), s.get_batch('a', [], repo, cache))
        for request in (dict(id='', limit=1), dict(id='x', limit=-1), dict(id='x', limit='1')):
            with self.assertRaises(ValueError):
                s.get_batch('a', [dict(id='x', limit=1), request], repo, cache)
            self.assertEqual([], repo.reads)
            self.assertEqual({}, cache)

if __name__ == '__main__':
    unittest.main(verbosity=2)
