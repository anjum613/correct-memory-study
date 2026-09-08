import unittest

from app.dependencies import Transport
from app.models import RelativeReference, Session
from app.service import fetch_same_origin


class SourceFunctionalTest(unittest.TestCase):
    def test_relative_resource_fetch(self):
        session = Session("https://app.example/base/", "sid=abc")
        transport = Transport()
        result = fetch_same_origin(RelativeReference("images/logo.png"), session, transport)
        self.assertEqual("https://app.example/base/images/logo.png", result.url)


if __name__ == "__main__":
    unittest.main()
