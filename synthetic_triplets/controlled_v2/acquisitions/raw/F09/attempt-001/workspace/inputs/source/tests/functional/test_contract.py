import unittest

from app.dependencies import Registry
from app.service import reserve_startup


class SourceFunctionalTest(unittest.TestCase):
    def test_unique_name_is_reserved(self):
        registry = Registry()
        result = reserve_startup("mailer", "alice", registry)
        self.assertEqual(("mailer", "alice"), (result.name, result.owner))


if __name__ == "__main__":
    unittest.main()
