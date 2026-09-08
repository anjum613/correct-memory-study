import unittest

from app.dependencies import Response
from app.service import prepare_download


class ExistingBehaviourTest(unittest.TestCase):
    def test_generated_filename_is_preserved(self):
        response = Response()
        result = prepare_download(3, response)
        self.assertEqual("job-3.csv", result.filename)
        self.assertIn("job-3.csv", response.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
