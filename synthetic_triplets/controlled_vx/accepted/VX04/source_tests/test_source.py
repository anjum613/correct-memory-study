import unittest
from app import service as s
from app import runtime as r

class Source(unittest.TestCase):
    def test_numeric_aggregation(self):
        got = s.render_numeric_table([dict(code=200, count=2), dict(code=100, count=1), dict(code=200, count=3)])
        self.assertEqual(6, got['total'])
        self.assertEqual([dict(code=100, label='100', count=1), dict(code=200, label='200', count=5)], got['groups'])
        self.assertEqual(2, got['html'].count('<tr>'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
