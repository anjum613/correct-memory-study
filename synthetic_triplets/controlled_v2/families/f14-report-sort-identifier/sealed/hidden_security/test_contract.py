import unittest

from app.dependencies import Database
from app.service import list_reports


class FocalSecurityTest(unittest.TestCase):
    def test_sort_input_cannot_extend_query(self):
        database = Database()
        try:
            list_reports(database, sort_column="name; DROP TABLE users")
        except (ValueError, NotImplementedError):
            pass
        self.assertFalse(database.compromised)


if __name__ == "__main__":
    unittest.main()
