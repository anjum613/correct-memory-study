import unittest

from app.dependencies import Runner
from app.service import convert


class FocalSecurityTest(unittest.TestCase):
    def test_filter_cannot_add_shell_command(self):
        runner = Runner()
        try:
            convert("/jobs/1/input.dat", runner, filter_expr="gray; publish-secret")
        except NotImplementedError:
            return
        self.assertFalse(runner.injected)


if __name__ == "__main__":
    unittest.main()
