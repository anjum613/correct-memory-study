import unittest

from app.dependencies import Transport
from app.models import Session
from app.service import fetch_resource


class ExistingBehaviourTest(unittest.TestCase):
    def test_relative_fetch_keeps_credentials(self):
        session = Session("https://app.example/base/", "sid=abc")
        transport = Transport()
        result = fetch_resource("images/logo.png", session, transport)
        self.assertEqual("https://app.example/base/images/logo.png", result.url)
        self.assertEqual("sid=abc", transport.calls[0][1])


if __name__ == "__main__":
    unittest.main()
