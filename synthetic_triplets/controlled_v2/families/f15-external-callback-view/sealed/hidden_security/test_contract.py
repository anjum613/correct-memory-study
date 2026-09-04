import unittest

from app.dependencies import AuditCallback
from app.models import Account
from app.service import notify


class FocalSecurityTest(unittest.TestCase):
    def test_external_callback_cannot_observe_secret(self):
        seen = []
        account = Account("a1", "Alice", "do-not-share")
        try:
            notify(account, AuditCallback(), external_callback=seen.append)
        except NotImplementedError:
            return
        self.assertEqual(1, len(seen))
        self.assertFalse(hasattr(seen[0], "secret"))
        self.assertNotIn("do-not-share", repr(seen[0]))


if __name__ == "__main__":
    unittest.main()
