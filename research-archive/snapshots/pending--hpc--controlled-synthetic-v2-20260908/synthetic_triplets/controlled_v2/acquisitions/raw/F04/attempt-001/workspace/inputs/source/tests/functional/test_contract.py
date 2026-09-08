import unittest

from app.dependencies import ExportStore
from app.service import export_generated


class SourceFunctionalTest(unittest.TestCase):
    def test_generated_export(self):
        store = ExportStore()
        receipt = export_generated(42, "summary", store)
        self.assertEqual("report-42.txt", receipt.path)
        self.assertEqual("summary", store.writes["/exports/report-42.txt"])


if __name__ == "__main__":
    unittest.main()
