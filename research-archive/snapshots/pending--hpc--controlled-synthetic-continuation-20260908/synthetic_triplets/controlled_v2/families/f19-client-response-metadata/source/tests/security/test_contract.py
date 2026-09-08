import unittest

from app.models import Response
from app.service import apply_generated


class SourceSecurityTest(unittest.TestCase):
    def test_generated_map_contains_only_reviewed_headers(self):
        keys = set(apply_generated(Response(), "req-17").headers)
        self.assertEqual({"X-Request-ID", "Cache-Control"}, keys)


if __name__ == "__main__":
    unittest.main()
