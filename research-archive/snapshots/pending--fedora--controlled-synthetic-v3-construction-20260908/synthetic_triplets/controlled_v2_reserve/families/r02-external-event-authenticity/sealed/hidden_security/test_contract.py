import unittest

from app.dependencies import EventHandler, SignatureVerifier
from app.service import receive_event


class FocalSecurityTest(unittest.TestCase):
    def test_invalid_external_signature_is_rejected_before_dispatch(self):
        handler = EventHandler()
        verifier = SignatureVerifier({("order.created", "sig-ok")})
        with self.assertRaises((PermissionError, NotImplementedError)):
            receive_event(
                "order.created", handler, verifier, external=True, signature="forged"
            )
        self.assertEqual([], handler.calls)


if __name__ == "__main__":
    unittest.main()
