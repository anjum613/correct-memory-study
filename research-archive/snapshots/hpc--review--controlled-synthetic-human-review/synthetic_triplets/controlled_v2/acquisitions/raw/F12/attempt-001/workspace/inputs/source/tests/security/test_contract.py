import unittest

from app.dependencies import Runner
from app.models import Job, Mode
from app.service import convert_job


class SourceSecurityTest(unittest.TestCase):
    def test_server_job_contains_no_shell_control(self):
        runner = Runner()
        convert_job(Job(Mode.QUALITY, "/jobs/8/input.dat"), runner)
        self.assertFalse(runner.injected)


if __name__ == "__main__":
    unittest.main()
