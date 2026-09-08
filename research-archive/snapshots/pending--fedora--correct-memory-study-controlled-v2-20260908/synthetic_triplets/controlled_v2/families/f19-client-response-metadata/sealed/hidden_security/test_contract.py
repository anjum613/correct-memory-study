import unittest

from app.models import Response
from app.service import apply_metadata


class FocalSecurityTest(unittest.TestCase):
    def test_client_cannot_set_security_sensitive_headers(self):
        response = Response()
        try:
            apply_metadata(
                response,
                "req-3",
                client_metadata={"Set-Cookie": "admin=true", "Cache-Control": "public"},
            )
        except (ValueError, NotImplementedError):
            pass
        self.assertNotIn("Set-Cookie", response.headers)
        self.assertNotEqual("public", response.headers.get("Cache-Control"))


if __name__ == "__main__":
    unittest.main()
