import unittest

from app.dependencies import Broker, Workspace
from app.models import Session
from app.service import read_document


class FocalSecurityTest(unittest.TestCase):
    def test_ungranted_workspace_cannot_be_read(self):
        broker = Broker({
            "personal": Workspace({"note": "mine"}),
            "payroll": Workspace({"note": "salary-secret"}),
        })
        session = Session("alice", "personal", frozenset({"personal"}))
        with self.assertRaises((PermissionError, NotImplementedError)):
            read_document(session, "note", broker, workspace="payroll")


if __name__ == "__main__":
    unittest.main()
