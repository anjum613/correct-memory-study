import unittest

from app.service import render_code


class SourceSecurityTest(unittest.TestCase):
    def test_integer_rendering_cannot_add_markup(self):
        rendered = render_code(-500).html
        self.assertEqual(2, rendered.count("<"))
        self.assertEqual(1, rendered.count("</"))


if __name__ == "__main__":
    unittest.main()
