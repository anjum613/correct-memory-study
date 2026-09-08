import unittest

from app.dependencies import Broker, Workspace
from app.models import Session
from app.service import read_document


class ExistingBehaviourTest(unittest.TestCase):
    def test_uses_session_default(self):
        broker = Broker({"personal": Workspace({"note": "mine"})})
        session = Session("alice", "personal", frozenset({"personal"}))
        self.assertEqual("mine", read_document(session, "note", broker))


if __name__ == "__main__":
    unittest.main()
