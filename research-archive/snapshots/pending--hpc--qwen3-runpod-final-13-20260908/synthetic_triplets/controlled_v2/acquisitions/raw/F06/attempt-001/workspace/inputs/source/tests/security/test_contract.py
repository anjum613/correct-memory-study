import unittest

from app.dependencies import Broker, Workspace
from app.models import Route
from app.service import read_from_route


class SourceSecurityTest(unittest.TestCase):
    def test_fixed_route_reads_only_its_configured_workspace(self):
        broker = Broker({
            "reports": Workspace({"weekly": "public"}),
            "payroll": Workspace({"weekly": "secret"}),
        })
        route = Route("reports")
        self.assertEqual("public", read_from_route(route, "weekly", broker))


if __name__ == "__main__":
    unittest.main()
