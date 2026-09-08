import unittest

from app.dependencies import validated_counts
from app.service import format_row


class ExistingBehaviourTest(unittest.TestCase):
    def test_count_only_row(self):
        self.assertEqual("2,10", format_row(validated_counts((2, 10))).text)


if __name__ == "__main__":
    unittest.main()
