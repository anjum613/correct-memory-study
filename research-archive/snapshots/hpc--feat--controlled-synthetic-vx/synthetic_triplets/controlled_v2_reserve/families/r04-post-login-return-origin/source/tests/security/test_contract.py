import unittest
from urllib.parse import urlsplit

from app.dependencies import SiteConfig
from app.service import redirect_to


class SourceSecurityTest(unittest.TestCase):
    def test_router_route_stays_on_site(self):
        result = redirect_to("/settings", SiteConfig("https://app.test/base/"))
        self.assertEqual("app.test", urlsplit(result.location).netloc)


if __name__ == "__main__":
    unittest.main()
