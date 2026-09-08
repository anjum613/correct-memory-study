import unittest

from app.dependencies import Database
from app.service import list_reports


class ExistingBehaviourTest(unittest.TestCase):
    def test_default_creation_order(self):
        database = Database()
        list_reports(database)
        self.assertTrue(database.queries[0].endswith("ORDER BY created_at"))


if __name__ == "__main__":
    unittest.main()
