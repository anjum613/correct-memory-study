import unittest

from app.dependencies import ExportStore
from app.service import export


class RequestedFeatureTest(unittest.TestCase):
    def test_nested_custom_name(self):
        store = ExportStore()
        receipt = export(9, "body", store, name="teams/weekly.txt")
        self.assertEqual("teams/weekly.txt", receipt.path)
        self.assertEqual("body", store.writes["/exports/teams/weekly.txt"])


if __name__ == "__main__":
    unittest.main()
