import unittest

from app.dependencies import EventHandler, SignatureVerifier
from app.service import receive_event


class RequestedFeatureTest(unittest.TestCase):
    def test_valid_external_event_is_dispatched(self):
        handler = EventHandler()
        verifier = SignatureVerifier({("order.created", "sig-ok")})
        receipt = receive_event(
            "order.created", handler, verifier, external=True, signature="sig-ok"
        )
        self.assertTrue(receipt.accepted)
        self.assertEqual(["order.created"], handler.calls)


if __name__ == "__main__":
    unittest.main()
