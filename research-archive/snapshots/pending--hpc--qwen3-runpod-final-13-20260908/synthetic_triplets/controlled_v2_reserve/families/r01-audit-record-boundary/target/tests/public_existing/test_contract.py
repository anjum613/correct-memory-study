import unittest

from app.dependencies import AuditSink
from app.service import write_login


class ExistingBehaviourTest(unittest.TestCase):
    def test_numeric_only_record_is_unchanged(self):
        sink = AuditSink()
        self.assertEqual("LOGIN user=9", write_login(9, sink).text)
        self.assertEqual(["LOGIN user=9"], sink.records)


if __name__ == "__main__":
    unittest.main()
