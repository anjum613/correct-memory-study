import unittest

from app.dependencies import Transport
from app.service import fetch_internal


class SourceSecurityTest(unittest.TestCase):
    def test_relative_reference_uses_fixed_authority(self):
        transport = Transport()
        fetch_internal("../health", transport)
        self.assertEqual(["https://api.internal.test/health"], transport.requested)


if __name__ == "__main__":
    unittest.main()
