import unittest

from app.service import render_code


class SourceFunctionalTest(unittest.TestCase):
    def test_numeric_badge(self):
        self.assertEqual('<span class="status">204</span>', render_code(204).html)


if __name__ == "__main__":
    unittest.main()
