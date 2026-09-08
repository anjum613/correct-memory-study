import unittest

from app.dependencies import Upload
from app.service import serve_upload


class ExistingBehaviourTest(unittest.TestCase):
    def test_download_remains_attachment(self):
        response = serve_upload(Upload("application/pdf", b"pdf"))
        self.assertEqual("attachment", response.headers["Content-Disposition"])
        self.assertEqual(b"pdf", response.body)


if __name__ == "__main__":
    unittest.main()
