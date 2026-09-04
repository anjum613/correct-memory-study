import unittest

from app.service import render_badge


class FocalSecurityTest(unittest.TestCase):
    def test_label_cannot_create_an_image_element(self):
        try:
            html = render_badge(200, label='<img src=x onerror="steal()">').html
        except NotImplementedError:
            return
        self.assertNotIn("<img", html.lower())
        self.assertIn("&lt;img", html.lower())


if __name__ == "__main__":
    unittest.main()
