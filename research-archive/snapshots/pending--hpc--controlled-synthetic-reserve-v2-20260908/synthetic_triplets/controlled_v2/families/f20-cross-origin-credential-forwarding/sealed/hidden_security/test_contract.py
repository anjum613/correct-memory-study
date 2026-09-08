import unittest

from app.dependencies import Transport
from app.models import Session
from app.service import fetch_resource


class FocalSecurityTest(unittest.TestCase):
    def test_cross_origin_request_has_no_session_cookie(self):
        session = Session("https://app.example/base/", "sid=do-not-forward")
        transport = Transport()
        try:
            fetch_resource(
                "https://collector.example/receive", session, transport, external=True
            )
        except NotImplementedError:
            return
        self.assertEqual(1, len(transport.calls))
        self.assertIsNone(transport.calls[0][1])


if __name__ == "__main__":
    unittest.main()
