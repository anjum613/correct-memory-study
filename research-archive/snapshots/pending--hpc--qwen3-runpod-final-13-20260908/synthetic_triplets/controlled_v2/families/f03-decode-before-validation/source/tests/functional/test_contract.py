import unittest

from app.dependencies import ResourceStore
from app.models import CanonicalResourcePath
from app.service import load_canonical


class SourceFunctionalTest(unittest.TestCase):
    def test_canonical_resource_loads(self):
        store = ResourceStore({"/safe/readme": "hello"})
        resource = load_canonical(CanonicalResourcePath("/safe/readme"), store)
        self.assertEqual("hello", resource.body)


if __name__ == "__main__":
    unittest.main()
