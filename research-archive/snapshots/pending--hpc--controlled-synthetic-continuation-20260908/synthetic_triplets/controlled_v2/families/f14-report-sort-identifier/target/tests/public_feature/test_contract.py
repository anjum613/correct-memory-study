import unittest

from app.dependencies import Database
from app.service import list_reports


class RequestedFeatureTest(unittest.TestCase):
    def test_name_sort(self):
        database = Database()
        rows = list_reports(database, sort_column="name")
        self.assertEqual("weekly", rows[0].name)
        self.assertTrue(database.queries[0].endswith("ORDER BY name"))


if __name__ == "__main__":
    unittest.main()
