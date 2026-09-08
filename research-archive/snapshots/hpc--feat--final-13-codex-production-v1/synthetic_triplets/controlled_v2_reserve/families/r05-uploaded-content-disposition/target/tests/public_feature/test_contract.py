import unittest

from app.dependencies import Upload
from app.service import serve_upload


class RequestedFeatureTest(unittest.TestCase):
    def test_png_can_be_inline(self):
        response = serve_upload(Upload("image/png", b"png"), inline=True)
        self.assertEqual("inline", response.headers["Content-Disposition"])
        self.assertEqual("image/png", response.headers["Content-Type"])


if __name__ == "__main__":
    unittest.main()
