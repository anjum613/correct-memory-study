import unittest

from app.dependencies import validated_counts
from app.service import format_counts


class SourceFunctionalTest(unittest.TestCase):
    def test_counts_are_joined(self):
        self.assertEqual("3,12,0", format_counts(validated_counts((3, 12, 0))).text)


if __name__ == "__main__":
    unittest.main()
