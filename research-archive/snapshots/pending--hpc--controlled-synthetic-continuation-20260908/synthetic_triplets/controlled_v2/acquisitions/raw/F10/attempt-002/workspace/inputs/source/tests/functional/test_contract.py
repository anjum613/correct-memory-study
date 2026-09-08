import unittest

from app.dependencies import Transport
from app.service import fetch_internal


class SourceFunctionalTest(unittest.TestCase):
    def test_relative_internal_fetch(self):
        transport = Transport()
        response = fetch_internal("status", transport)
        self.assertEqual("https://api.internal.test/v1/status", response.url)


if __name__ == "__main__":
    unittest.main()
