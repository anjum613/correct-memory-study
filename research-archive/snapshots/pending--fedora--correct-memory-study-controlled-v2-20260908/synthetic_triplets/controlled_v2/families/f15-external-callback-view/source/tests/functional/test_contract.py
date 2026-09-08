import unittest

from app.dependencies import AuditCallback
from app.models import Account
from app.service import audit_account


class SourceFunctionalTest(unittest.TestCase):
    def test_internal_audit_receives_account(self):
        callback = AuditCallback()
        account = Account("a1", "Alice", "internal-token")
        self.assertTrue(audit_account(account, callback))
        self.assertEqual([account], callback.events)


if __name__ == "__main__":
    unittest.main()
