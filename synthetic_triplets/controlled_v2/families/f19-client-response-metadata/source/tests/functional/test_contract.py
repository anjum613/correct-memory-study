import unittest

from app.models import Response
from app.service import apply_generated


class SourceFunctionalTest(unittest.TestCase):
    def test_generated_headers(self):
        response = apply_generated(Response(), "req-17")
        self.assertEqual("req-17", response.headers["X-Request-ID"])
        self.assertEqual("private", response.headers["Cache-Control"])


if __name__ == "__main__":
    unittest.main()
