import unittest

from app.dependencies import SiteConfig
from app.service import redirect_to


class SourceFunctionalTest(unittest.TestCase):
    def test_local_route_is_resolved(self):
        result = redirect_to("account", SiteConfig("https://app.test/base/"))
        self.assertEqual("https://app.test/base/account", result.location)


if __name__ == "__main__":
    unittest.main()
