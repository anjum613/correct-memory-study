import unittest

from app.dependencies import AuditSink
from app.service import write_login


class SourceFunctionalTest(unittest.TestCase):
    def test_numeric_login_record(self):
        sink = AuditSink()
        record = write_login(42, sink)
        self.assertEqual("LOGIN user=42", record.text)
        self.assertEqual([record.text], sink.records)


if __name__ == "__main__":
    unittest.main()
