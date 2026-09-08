import unittest

from app.dependencies import Runner
from app.models import Job, Mode
from app.service import convert_job


class SourceFunctionalTest(unittest.TestCase):
    def test_internal_job_runs(self):
        runner = Runner()
        result = convert_job(Job(Mode.FAST, "/jobs/17/input.dat"), runner)
        self.assertTrue(result.ok)
        self.assertEqual(("shell", "converter --mode fast /jobs/17/input.dat"), runner.calls[0])


if __name__ == "__main__":
    unittest.main()
