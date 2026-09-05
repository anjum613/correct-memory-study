import unittest
from app import service as s
from app import runtime as r

class Existing(unittest.TestCase):
    def test_fetch_one(self):
        session = r.Session(('HTTPS', 'APP.EXAMPLE', 443), 'simulation-marker')
        transport = r.Transport()
        self.assertEqual('app.example:one', s.fetch_one('one', session, transport))
        self.assertEqual((('https', 'app.example', 443), 'one', 'simulation-marker'), transport.calls[0])

if __name__ == '__main__':
    unittest.main(verbosity=2)
