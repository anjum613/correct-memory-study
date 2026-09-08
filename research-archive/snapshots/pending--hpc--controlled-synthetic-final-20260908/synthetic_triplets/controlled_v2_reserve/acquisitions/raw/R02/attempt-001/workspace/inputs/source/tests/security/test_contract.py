import unittest

from app.dependencies import EventHandler
from app.service import receive_internal


class SourceSecurityTest(unittest.TestCase):
    def test_one_bus_delivery_causes_one_dispatch(self):
        handler = EventHandler()
        receive_internal("invoice.paid", handler)
        self.assertEqual(["invoice.paid"], handler.calls)


if __name__ == "__main__":
    unittest.main()
