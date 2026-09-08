import unittest

from app.dependencies import AuditCallback
from app.models import Account
from app.service import audit_account


class SourceSecurityTest(unittest.TestCase):
    def test_only_application_callback_receives_internal_object(self):
        callback = AuditCallback()
        account = Account("a1", "Alice", "internal-token")
        audit_account(account, callback)
        self.assertIs(account, callback.events[0])
        self.assertEqual(1, len(callback.events))


if __name__ == "__main__":
    unittest.main()
