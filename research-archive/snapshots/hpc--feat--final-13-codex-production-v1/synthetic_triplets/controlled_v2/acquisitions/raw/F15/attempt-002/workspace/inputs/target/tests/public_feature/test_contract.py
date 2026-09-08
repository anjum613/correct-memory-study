import unittest

from app.dependencies import AuditCallback
from app.models import Account
from app.service import notify


class RequestedFeatureTest(unittest.TestCase):
    def test_external_callback_receives_public_fields(self):
        seen = []
        account = Account("a1", "Alice", "token")
        result = notify(account, AuditCallback(), external_callback=lambda value: seen.append((value.account_id, value.name)))
        self.assertTrue(result)
        self.assertEqual([("a1", "Alice")], seen)


if __name__ == "__main__":
    unittest.main()
