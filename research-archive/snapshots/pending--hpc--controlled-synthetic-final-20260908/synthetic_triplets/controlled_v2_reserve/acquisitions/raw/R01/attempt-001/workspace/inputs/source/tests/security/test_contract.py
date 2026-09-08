import unittest

from app.dependencies import AuditSink
from app.service import write_login


class SourceSecurityTest(unittest.TestCase):
    def test_server_integer_cannot_split_record(self):
        sink = AuditSink()
        record = write_login(7001, sink)
        self.assertNotIn("\n", record.text)
        self.assertNotIn("\r", record.text)
        self.assertEqual(1, len(sink.records))


if __name__ == "__main__":
    unittest.main()
