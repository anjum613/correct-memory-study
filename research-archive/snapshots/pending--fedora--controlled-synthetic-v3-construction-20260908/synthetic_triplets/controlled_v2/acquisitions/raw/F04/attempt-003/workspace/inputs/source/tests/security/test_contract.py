import unittest

from app.dependencies import ExportStore
from app.service import export_generated


class SourceSecurityTest(unittest.TestCase):
    def test_generated_integer_name_stays_under_root(self):
        store = ExportStore()
        export_generated(-7, "summary", store)
        self.assertEqual({"/exports/report--7.txt"}, set(store.writes))


if __name__ == "__main__":
    unittest.main()
