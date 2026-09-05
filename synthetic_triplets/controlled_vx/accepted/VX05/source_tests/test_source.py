import unittest
from app import service as s
from app import runtime as r

class Source(unittest.TestCase):
    def test_local_projection(self):
        repo = r.Repository({('a', 'doc'): 'alpha', ('b', 'doc'): 'beta'})
        requests = [dict(id='doc', limit=2), dict(id='doc', limit=9)]
        for user, expected in (('a', ['al', 'alpha']), ('b', ['be', 'beta'])):
            got = s.get_local_batch(user, requests, repo, {})
            self.assertEqual(expected, [row['text'] for row in got['rows']])
            self.assertEqual(1, got['repository_reads'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
