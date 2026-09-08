import unittest

from app.service import render_badge


class ExistingBehaviourTest(unittest.TestCase):
    def test_numeric_fallback(self):
        self.assertEqual('<span class="status">200</span>', render_badge(200).html)


if __name__ == "__main__":
    unittest.main()
