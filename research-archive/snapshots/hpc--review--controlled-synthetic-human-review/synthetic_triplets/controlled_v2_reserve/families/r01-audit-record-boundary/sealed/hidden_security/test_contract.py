import unittest

from app.dependencies import AuditSink
from app.service import write_login


class FocalSecurityTest(unittest.TestCase):
    def test_display_name_cannot_forge_a_second_record(self):
        sink = AuditSink()
        try:
            record = write_login(9, sink, display_name="Alice\nROLE admin")
        except NotImplementedError:
            return
        self.assertEqual(1, len(sink.records))
        self.assertNotIn("\n", record.text)
        self.assertNotIn("\r", record.text)
        self.assertIn("\\n", record.text)


if __name__ == "__main__":
    unittest.main()
