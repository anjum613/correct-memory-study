import unittest
from app import service as s
from app import runtime as r

class Existing(unittest.TestCase):
    def test_badge(self):
        for code in (0, 200, -4):
            self.assertEqual(f'<span class="status">{code}</span>', s.badge(code))

if __name__ == '__main__':
    unittest.main(verbosity=2)
