import unittest

from app.dependencies import ImageAsset
from app.service import serve_preview


class SourceFunctionalTest(unittest.TestCase):
    def test_generated_png_is_inline(self):
        response = serve_preview(ImageAsset("image/png", b"png"))
        self.assertEqual("inline", response.headers["Content-Disposition"])
        self.assertEqual(b"png", response.body)


if __name__ == "__main__":
    unittest.main()
