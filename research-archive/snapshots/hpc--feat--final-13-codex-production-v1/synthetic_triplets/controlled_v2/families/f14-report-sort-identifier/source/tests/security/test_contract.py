import unittest

from app.dependencies import Database
from app.service import list_recent


class SourceSecurityTest(unittest.TestCase):
    def test_fixed_identifier_contains_no_extra_statement(self):
        database = Database()
        list_recent(database)
        self.assertFalse(database.compromised)


if __name__ == "__main__":
    unittest.main()
