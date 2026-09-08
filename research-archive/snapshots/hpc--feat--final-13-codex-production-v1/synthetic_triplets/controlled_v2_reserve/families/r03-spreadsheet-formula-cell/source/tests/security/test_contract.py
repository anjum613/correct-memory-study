import unittest

from app.dependencies import validated_counts
from app.service import format_counts


class SourceSecurityTest(unittest.TestCase):
    def test_validated_decimal_cells_are_not_formulas(self):
        row = format_counts(validated_counts((0, 7, 21))).text
        self.assertTrue(all(cell[:1] not in "=+-@" for cell in row.split(",")))


if __name__ == "__main__":
    unittest.main()
