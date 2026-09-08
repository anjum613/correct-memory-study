import unittest

from app.service import format_row


class RequestedFeatureTest(unittest.TestCase):
    def test_plain_labels_are_exported(self):
        self.assertEqual("North,South", format_row((), labels=("North", "South")).text)


if __name__ == "__main__":
    unittest.main()
