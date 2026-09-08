import unittest

from app.dependencies import Broker, Workspace
from app.models import Route
from app.service import read_from_route


class SourceFunctionalTest(unittest.TestCase):
    def test_reads_server_routed_workspace(self):
        broker = Broker({"reports": Workspace({"weekly": "ready"})})
        self.assertEqual("ready", read_from_route(Route("reports"), "weekly", broker))


if __name__ == "__main__":
    unittest.main()
