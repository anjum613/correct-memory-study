import unittest

from app.dependencies import SiteConfig
from app.service import redirect_after_login


class ExistingBehaviourTest(unittest.TestCase):
    def test_default_route_is_preserved(self):
        result = redirect_after_login("account", SiteConfig("https://app.test/base/"))
        self.assertEqual("https://app.test/base/account", result.location)


if __name__ == "__main__":
    unittest.main()
