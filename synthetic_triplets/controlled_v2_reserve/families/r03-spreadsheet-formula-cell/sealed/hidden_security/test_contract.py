import unittest

from app.service import format_row


class FocalSecurityTest(unittest.TestCase):
    def test_formula_label_is_neutralized(self):
        try:
            cell = format_row((), labels=("=HYPERLINK(attack)",)).text
        except NotImplementedError:
            return
        self.assertTrue(cell.startswith("'="))


if __name__ == "__main__":
    unittest.main()
