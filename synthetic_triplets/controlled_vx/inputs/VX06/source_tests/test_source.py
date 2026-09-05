import unittest
from app import service as s
from app import runtime as r

class Source(unittest.TestCase):
    def test_same_origin_manifest(self):
        session = r.Session(('https', 'app.example', 443), 'simulation-marker')
        transport = r.Transport()
        got = s.fetch_local_manifest([dict(id='a', path='one'), dict(id='b', path='one')], session, transport)
        self.assertEqual(1, got['fetches'])
        self.assertEqual(['simulation-marker'], [call[2] for call in transport.calls])
        self.assertEqual(['a', 'b'], [row['id'] for row in got['rows']])

if __name__ == '__main__':
    unittest.main(verbosity=2)
