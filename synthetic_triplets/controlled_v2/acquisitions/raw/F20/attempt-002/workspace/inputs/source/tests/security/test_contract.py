import unittest

from app.models import RelativeReference


class SourceSecurityTest(unittest.TestCase):
    def test_source_reference_cannot_name_external_origin(self):
        with self.assertRaises(ValueError):
            RelativeReference("https://collector.example/receive")


if __name__ == "__main__":
    unittest.main()
