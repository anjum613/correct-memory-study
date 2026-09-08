import unittest

from app.dependencies import ExportStore
from app.service import export


class FocalSecurityTest(unittest.TestCase):
    def test_parent_name_cannot_write_outside_export_root(self):
        store = ExportStore()
        try:
            export(9, "replacement", store, name="../private/audit.txt")
        except (ValueError, NotImplementedError):
            pass
        self.assertNotIn("/private/audit.txt", store.writes)


if __name__ == "__main__":
    unittest.main()
