import unittest

from app.dependencies import ResourceStore
from app.service import load


class ExistingBehaviourTest(unittest.TestCase):
    def test_canonical_resource_loads(self):
        store = ResourceStore({"/safe/readme": "hello"})
        resource = load("/safe/readme", store)
        self.assertEqual(("/safe/readme", "hello"), (resource.path, resource.body))


if __name__ == "__main__":
    unittest.main()
