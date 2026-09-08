import unittest

from app.dependencies import Database
from app.service import list_recent


class SourceFunctionalTest(unittest.TestCase):
    def test_creation_order_query(self):
        database = Database()
        rows = list_recent(database)
        self.assertEqual("weekly", rows[0].name)
        self.assertTrue(database.queries[0].endswith("ORDER BY created_at"))


if __name__ == "__main__":
    unittest.main()
