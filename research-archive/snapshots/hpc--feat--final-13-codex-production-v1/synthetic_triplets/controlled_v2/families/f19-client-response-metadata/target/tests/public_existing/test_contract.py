import unittest

from app.models import Response
from app.service import apply_metadata


class ExistingBehaviourTest(unittest.TestCase):
    def test_generated_metadata_is_preserved(self):
        response = apply_metadata(Response(), "req-3")
        self.assertEqual(
            {"X-Request-ID": "req-3", "Cache-Control": "private"}, response.headers
        )


if __name__ == "__main__":
    unittest.main()
