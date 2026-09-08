import unittest

from app.dependencies import ResourceStore
from app.service import load


class FocalSecurityTest(unittest.TestCase):
    def test_encoded_parent_cannot_escape_namespace(self):
        store = ResourceStore({"/secret": "outside", "/safe/readme": "inside"})
        with self.assertRaises((PermissionError, NotImplementedError, ValueError)):
            load("/safe/%2e%2e/secret", store, encoded=True)


if __name__ == "__main__":
    unittest.main()
