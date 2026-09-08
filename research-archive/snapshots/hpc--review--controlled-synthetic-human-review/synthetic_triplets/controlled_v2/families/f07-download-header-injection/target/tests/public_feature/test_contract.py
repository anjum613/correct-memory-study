import unittest

from app.dependencies import Response
from app.service import prepare_download


class RequestedFeatureTest(unittest.TestCase):
    def test_custom_filename_is_used(self):
        response = Response()
        result = prepare_download(3, response, filename="quarterly report.csv")
        self.assertEqual("quarterly report.csv", result.filename)
        self.assertIn("quarterly", response.headers["Content-Disposition"])
        self.assertIn("report.csv", response.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
