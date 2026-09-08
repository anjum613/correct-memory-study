import unittest

from app.dependencies import Transport
from app.models import Session
from app.service import fetch_resource


class RequestedFeatureTest(unittest.TestCase):
    def test_external_resource_is_fetched(self):
        session = Session("https://app.example/base/", "sid=abc")
        transport = Transport()
        result = fetch_resource(
            "https://cdn.example/assets/logo.png", session, transport, external=True
        )
        self.assertEqual("https://cdn.example/assets/logo.png", result.url)
        self.assertEqual("resource", result.body)


if __name__ == "__main__":
    unittest.main()
