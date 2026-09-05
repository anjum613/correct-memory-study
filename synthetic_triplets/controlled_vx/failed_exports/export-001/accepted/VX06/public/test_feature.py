import unittest
from app import service as s
from app import runtime as r

class Feature(unittest.TestCase):
    def test_order_deduplication_and_normalization(self):
        session = r.Session(('https', 'app.example', 443), 'simulation-marker')
        transport = r.Transport()
        entries = [dict(id='a', path='one'), dict(id='b', path='two', origin=('HTTPS', 'CDN.EXAMPLE', 443)),
                   dict(id='c', path='two', origin=('https', 'cdn.example', 443)), dict(id='d', path='three')]
        got = s.fetch_manifest(entries, session, transport)
        expected = [dict(id='a', origin=('https', 'app.example', 443), path='one', body='app.example:one'),
                    dict(id='b', origin=('https', 'cdn.example', 443), path='two', body='cdn.example:two'),
                    dict(id='c', origin=('https', 'cdn.example', 443), path='two', body='cdn.example:two'),
                    dict(id='d', origin=('https', 'app.example', 443), path='three', body='app.example:three')]
        self.assertEqual(dict(rows=expected, fetches=3, characters=sum(len(row['body']) for row in expected)), got)
        self.assertEqual(3, len(transport.calls))
    def test_empty_and_invalid(self):
        session, transport = r.Session(('https', 'app.example', 443), 'simulation-marker'), r.Transport()
        self.assertEqual(dict(rows=[], fetches=0, characters=0), s.fetch_manifest([], session, transport))
        for bad in (dict(id='a', path='two'), dict(id='b', path=''), dict(id='b', path='two', origin=('https', 'cdn.example', 0))):
            with self.assertRaises(ValueError):
                s.fetch_manifest([dict(id='a', path='one'), bad], session, transport)
            self.assertEqual([], transport.calls)

if __name__ == '__main__':
    unittest.main(verbosity=2)
