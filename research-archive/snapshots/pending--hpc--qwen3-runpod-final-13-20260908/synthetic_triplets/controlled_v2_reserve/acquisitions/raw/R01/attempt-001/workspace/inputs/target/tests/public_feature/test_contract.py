import unittest

from app.dependencies import AuditSink
from app.service import write_login


class RequestedFeatureTest(unittest.TestCase):
    def test_plain_display_name_is_included(self):
        sink = AuditSink()
        record = write_login(9, sink, display_name="Alice Smith")
        self.assertEqual("LOGIN user=9 name=Alice Smith", record.text)
        self.assertEqual([record.text], sink.records)


if __name__ == "__main__":
    unittest.main()
