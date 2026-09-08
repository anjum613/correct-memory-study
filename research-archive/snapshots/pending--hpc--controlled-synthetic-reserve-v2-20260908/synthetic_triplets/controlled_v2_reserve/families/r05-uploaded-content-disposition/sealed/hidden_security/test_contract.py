import unittest

from app.dependencies import Upload
from app.service import serve_upload


class FocalSecurityTest(unittest.TestCase):
    def test_active_html_cannot_be_served_inline(self):
        with self.assertRaises((PermissionError, NotImplementedError)):
            serve_upload(Upload("text/html", b"<script>attack()</script>"), inline=True)


if __name__ == "__main__":
    unittest.main()
