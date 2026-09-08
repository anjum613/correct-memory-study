import unittest

from app.models import CanonicalResourcePath


class SourceSecurityTest(unittest.TestCase):
    def test_router_type_rejects_noncanonical_parent_path(self):
        with self.assertRaises(ValueError):
            CanonicalResourcePath("/safe/../secret")


if __name__ == "__main__":
    unittest.main()
