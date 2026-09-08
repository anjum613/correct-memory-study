import unittest

from app.dependencies import IntegrationConfig, Transport
from app.service import fetch_resource


class RequestedFeatureTest(unittest.TestCase):
    def test_approved_custom_base(self):
        config = IntegrationConfig(
            "https://api.internal.test/v1/",
            {"https://api.internal.test", "https://partner.example"},
        )
        response = fetch_resource(
            "status", config, Transport(), base_url="https://partner.example/api/"
        )
        self.assertEqual("https://partner.example/api/status", response.url)


if __name__ == "__main__":
    unittest.main()
