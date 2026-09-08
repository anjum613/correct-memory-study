import unittest

from app.dependencies import IntegrationConfig, Transport
from app.service import fetch_resource


class ExistingBehaviourTest(unittest.TestCase):
    def test_default_base(self):
        config = IntegrationConfig(
            "https://api.internal.test/v1/", {"https://api.internal.test"}
        )
        response = fetch_resource("status", config, Transport())
        self.assertEqual("https://api.internal.test/v1/status", response.url)


if __name__ == "__main__":
    unittest.main()
