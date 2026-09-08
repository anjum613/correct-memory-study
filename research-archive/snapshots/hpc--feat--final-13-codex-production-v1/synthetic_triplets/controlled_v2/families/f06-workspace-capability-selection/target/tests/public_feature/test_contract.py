import unittest

from app.dependencies import Broker, Workspace
from app.models import Session
from app.service import read_document


class RequestedFeatureTest(unittest.TestCase):
    def test_selects_another_granted_workspace(self):
        broker = Broker({
            "personal": Workspace({"note": "mine"}),
            "team": Workspace({"note": "shared"}),
        })
        session = Session("alice", "personal", frozenset({"personal", "team"}))
        self.assertEqual("shared", read_document(session, "note", broker, workspace="team"))


if __name__ == "__main__":
    unittest.main()
