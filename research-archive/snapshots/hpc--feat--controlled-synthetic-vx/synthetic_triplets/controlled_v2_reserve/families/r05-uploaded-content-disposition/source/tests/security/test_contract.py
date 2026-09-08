import unittest

from app.dependencies import ImageAsset
from app.service import serve_preview


class SourceSecurityTest(unittest.TestCase):
    def test_pipeline_assigns_passive_image_type(self):
        response = serve_preview(ImageAsset("image/jpeg", b"jpeg"))
        self.assertIn(response.headers["Content-Type"], {"image/jpeg", "image/png"})


if __name__ == "__main__":
    unittest.main()
