import unittest

from app.dependencies import Runner
from app.service import convert


class RequestedFeatureTest(unittest.TestCase):
    def test_plain_filter_is_supplied(self):
        runner = Runner()
        result = convert("/jobs/1/input.dat", runner, filter_expr="grayscale")
        self.assertTrue(result.ok)
        self.assertIn("grayscale", str(runner.calls[0]))


if __name__ == "__main__":
    unittest.main()
