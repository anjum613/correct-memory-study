import unittest

from app.dependencies import ResourceStore
from app.service import load


class RequestedFeatureTest(unittest.TestCase):
    def test_encoded_safe_component_loads(self):
        store = ResourceStore({"/safe/readme": "hello"})
        resource = load("/safe/%72eadme", store, encoded=True)
        self.assertEqual(("/safe/readme", "hello"), (resource.path, resource.body))


if __name__ == "__main__":
    unittest.main()
