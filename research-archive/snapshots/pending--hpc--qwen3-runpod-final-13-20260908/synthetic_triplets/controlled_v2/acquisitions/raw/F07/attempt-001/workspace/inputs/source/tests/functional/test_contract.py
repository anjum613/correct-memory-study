import unittest

from app.dependencies import Response
from app.service import prepare_generated


class SourceFunctionalTest(unittest.TestCase):
    def test_generated_header(self):
        response = Response()
        result = prepare_generated(17, response)
        self.assertEqual("job-17.csv", result.filename)
        self.assertEqual('attachment; filename="job-17.csv"', response.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
