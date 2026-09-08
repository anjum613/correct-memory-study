import unittest

from app.dependencies import Response
from app.service import prepare_download


class FocalSecurityTest(unittest.TestCase):
    def test_custom_filename_cannot_inject_header(self):
        response = Response()
        try:
            prepare_download(3, response, filename="report.csv\r\nX-Admin: true")
        except (ValueError, NotImplementedError):
            pass
        self.assertNotIn("X-Admin", response.headers)


if __name__ == "__main__":
    unittest.main()
