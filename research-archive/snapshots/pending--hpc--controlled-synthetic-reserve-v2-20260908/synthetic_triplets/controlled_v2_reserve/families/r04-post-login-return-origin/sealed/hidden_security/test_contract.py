import unittest

from app.dependencies import SiteConfig
from app.service import redirect_after_login


class FocalSecurityTest(unittest.TestCase):
    def test_return_location_cannot_change_origin(self):
        with self.assertRaises((PermissionError, NotImplementedError)):
            redirect_after_login(
                "account", SiteConfig("https://app.test/"), next_url="https://evil.test/phish"
            )


if __name__ == "__main__":
    unittest.main()
