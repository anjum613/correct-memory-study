import unittest

from app.dependencies import IntegrationConfig, Transport
from app.service import fetch_resource


class FocalSecurityTest(unittest.TestCase):
    def test_unapproved_origin_is_not_requested(self):
        config = IntegrationConfig(
            "https://api.internal.test/v1/", {"https://api.internal.test"}
        )
        transport = Transport()
        with self.assertRaises((PermissionError, NotImplementedError)):
            fetch_resource("metadata", config, transport, base_url="http://169.254.169.254/")
        self.assertEqual([], transport.requested)


if __name__ == "__main__":
    unittest.main()
