import unittest

from app.dependencies import Runner
from app.service import convert


class ExistingBehaviourTest(unittest.TestCase):
    def test_conversion_without_filter(self):
        runner = Runner()
        result = convert("/jobs/1/input.dat", runner)
        self.assertTrue(result.ok)
        self.assertEqual("/jobs/1/input.dat", result.source)


if __name__ == "__main__":
    unittest.main()
