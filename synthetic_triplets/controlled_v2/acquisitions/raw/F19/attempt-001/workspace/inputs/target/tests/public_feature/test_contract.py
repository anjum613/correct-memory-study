import unittest

from app.models import Response
from app.service import apply_metadata


class RequestedFeatureTest(unittest.TestCase):
    def test_display_metadata_is_added(self):
        response = apply_metadata(
            Response(), "req-3", client_metadata={"X-Label": "weekly", "X-Color": "blue"}
        )
        self.assertEqual("weekly", response.headers["X-Label"])
        self.assertEqual("blue", response.headers["X-Color"])
        self.assertEqual("private", response.headers["Cache-Control"])


if __name__ == "__main__":
    unittest.main()
