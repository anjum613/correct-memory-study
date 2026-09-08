import unittest

from app.dependencies import SiteConfig
from app.service import redirect_after_login


class RequestedFeatureTest(unittest.TestCase):
    def test_parent_relative_return_is_resolved(self):
        result = redirect_after_login(
            "account", SiteConfig("https://app.test/users/login/"), next_url="../dashboard"
        )
        self.assertEqual("https://app.test/users/dashboard", result.location)


if __name__ == "__main__":
    unittest.main()
