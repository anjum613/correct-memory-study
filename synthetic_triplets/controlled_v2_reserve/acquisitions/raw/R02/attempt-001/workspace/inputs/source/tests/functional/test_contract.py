import unittest

from app.dependencies import EventHandler
from app.service import receive_internal


class SourceFunctionalTest(unittest.TestCase):
    def test_authenticated_event_is_dispatched(self):
        handler = EventHandler()
        receipt = receive_internal("order.created", handler)
        self.assertTrue(receipt.accepted)
        self.assertEqual(["order.created"], handler.calls)


if __name__ == "__main__":
    unittest.main()
