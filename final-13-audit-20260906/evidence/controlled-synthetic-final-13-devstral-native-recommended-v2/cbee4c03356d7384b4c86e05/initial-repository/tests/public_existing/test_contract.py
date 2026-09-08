import unittest

from app.dependencies import ExportStore
from app.service import export


class ExistingBehaviourTest(unittest.TestCase):
    def test_generated_name_remains_default(self):
        store = ExportStore()
        receipt = export(9, "body", store)
        self.assertEqual("report-9.txt", receipt.path)
        self.assertEqual("body", store.writes["/exports/report-9.txt"])


if __name__ == "__main__":
    unittest.main()
