import unittest

from app.dependencies import AuditCallback
from app.models import Account
from app.service import notify


class ExistingBehaviourTest(unittest.TestCase):
    def test_audit_callback_is_preserved(self):
        audit = AuditCallback()
        account = Account("a1", "Alice", "token")
        self.assertTrue(notify(account, audit))
        self.assertEqual([account], audit.events)


if __name__ == "__main__":
    unittest.main()
