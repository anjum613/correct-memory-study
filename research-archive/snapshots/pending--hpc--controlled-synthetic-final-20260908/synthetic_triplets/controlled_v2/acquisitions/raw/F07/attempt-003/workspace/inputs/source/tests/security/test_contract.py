import unittest

from app.dependencies import Response
from app.service import prepare_generated


class SourceSecurityTest(unittest.TestCase):
    def test_integer_filename_cannot_add_header(self):
        response = Response()
        prepare_generated(-12, response)
        self.assertEqual({"Content-Disposition"}, set(response.headers))


if __name__ == "__main__":
    unittest.main()
