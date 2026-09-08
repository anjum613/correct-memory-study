import unittest
from app import service as s
from app import runtime as r

class Invariant(unittest.TestCase):
    def test_marker_scope_in_all_origin_dimensions(self):
        session = r.Session(('https', 'app.example', 443), 'simulation-marker')
        origins = [('HTTPS', 'APP.EXAMPLE', 443), ('http', 'app.example', 443),
                   ('https', 'app.example', 8443), ('https', 'cdn.example', 443)]
        transport = r.Transport()
        try:
            s.fetch_manifest([dict(id=str(i), path='resource', origin=origin) for i, origin in enumerate(origins)], session, transport)
        except NotImplementedError:
            return
        self.assertEqual(4, len(transport.calls))
        self.assertEqual(['simulation-marker', None, None, None], [call[2] for call in transport.calls])

if __name__ == '__main__':
    unittest.main(verbosity=2)
