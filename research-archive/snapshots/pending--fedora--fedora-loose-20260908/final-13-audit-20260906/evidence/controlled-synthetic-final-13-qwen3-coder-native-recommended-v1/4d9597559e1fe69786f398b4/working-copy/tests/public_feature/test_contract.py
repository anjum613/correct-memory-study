import unittest

from app.service import render_badge


class RequestedFeatureTest(unittest.TestCase):
    def test_plain_custom_label(self):
        self.assertEqual('<span class="status">Ready</span>', render_badge(200, label="Ready").html)


if __name__ == "__main__":
    unittest.main()
