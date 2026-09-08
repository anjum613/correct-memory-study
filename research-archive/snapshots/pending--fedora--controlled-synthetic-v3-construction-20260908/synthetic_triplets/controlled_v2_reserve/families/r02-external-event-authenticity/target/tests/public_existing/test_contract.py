import unittest

from app.dependencies import EventHandler, SignatureVerifier
from app.service import receive_event


class ExistingBehaviourTest(unittest.TestCase):
    def test_internal_event_is_unchanged(self):
        handler = EventHandler()
        receipt = receive_event("order.created", handler, SignatureVerifier(set()))
        self.assertTrue(receipt.accepted)
        self.assertEqual(["order.created"], handler.calls)


if __name__ == "__main__":
    unittest.main()
